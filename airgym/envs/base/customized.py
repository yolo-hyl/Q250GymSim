import numpy as np
import torch

import torch.nn.functional as F

from isaacgym import gymtorch, gymapi
from airgym.utils.torch_utils import *

from airgym.envs.base.base_task import BaseTask
from airgym.envs.base.customized_config import CustomizedCfg

from airgym.assets.asset_manager import AssetManager

import pytorch3d.transforms as T
import cv2
import os

from rlPx4Controller.pyParallelControl import ParallelRateControl,ParallelVelControl,ParallelAttiControl,ParallelPosControl

LENGTH = 8.0
WIDTH = 8.0
FLY_HEIGHT = 1.0

def compute_yaw_diff(a: torch.Tensor, b: torch.Tensor):
    """Compute the difference between two sets of Euler angles. a & b in [-pi, pi]"""
    diff = b - a
    diff = torch.where(diff < -torch.pi, diff + 2*torch.pi, diff)
    diff = torch.where(diff > torch.pi, diff - 2*torch.pi, diff)
    return diff

class Customized(BaseTask):

    def __init__(self, cfg: CustomizedCfg, sim_params, physics_engine, sim_device, headless):
        assert cfg.env.ctl_mode is not None, "Please specify one control mode!"
        assert cfg.env.asset_model is not None, "Please specify one asset model!"
        assert cfg.asset_config.include_robot[cfg.env.asset_model] is not None, "Please append asset config in your task config!"
        import copy
        new_cfg = copy.deepcopy(cfg)
        new_cfg.asset_config.include_robot = {cfg.env.asset_model: cfg.asset_config.include_robot[cfg.env.asset_model]}
        self.cfg = new_cfg
        assert cfg.env.ctl_mode is not None, "Please specify one control mode!"
        print("ctl mode =========== ", cfg.env.ctl_mode)
        self.ctl_mode = cfg.env.ctl_mode
        self.cfg.env.num_actions = 5 if cfg.env.ctl_mode == "atti" else 4
        self.max_episode_length = int(self.cfg.env.episode_length_s / self.cfg.sim.dt)
        self.debug_viz = False
        num_actors = 1

        self.sim_params = sim_params
        self.physics_engine = physics_engine
        self.sim_device_id = sim_device
        self.headless = headless

        self.asset_manager = AssetManager(self.cfg, sim_device)
        
        super().__init__(self.cfg, sim_params, physics_engine, sim_device, headless)
        self.root_tensor = self.gym.acquire_actor_root_state_tensor(self.sim)
        self.contact_force_tensor = self.gym.acquire_net_contact_force_tensor(self.sim)

        self.gym.refresh_actor_root_state_tensor(self.sim)
        self.gym.refresh_net_contact_force_tensor(self.sim)

        num_actors = self.asset_manager.get_env_actor_count() # Number of actors including robots and env assets in the environment
        num_env_assets = self.asset_manager.get_env_asset_count() # Number of env assets
        robot_num_bodies = self.asset_manager.get_robot_num_bodies() # Number of robots bodies in environment
        env_asset_link_count = self.asset_manager.get_env_asset_link_count() # Number of env assets links in the environment
        env_boundary_count = self.asset_manager.get_env_boundary_count() # Number of env boundaries in the environment
        self.num_assets = num_env_assets - env_boundary_count # # Number of env assets that can be randomly placed
        bodies_per_env = env_asset_link_count + robot_num_bodies
        
        self.vec_root_tensor = gymtorch.wrap_tensor(
            self.root_tensor).view(self.num_envs, num_actors, 13)

        self.root_states = self.vec_root_tensor[:, 0, :]
        self.root_positions = self.root_states[..., 0:3]
        self.root_quats = self.root_states[..., 3:7] # x,y,z,w
        self.root_linvels = self.root_states[..., 7:10]
        self.root_angvels = self.root_states[..., 10:13]

        self.privileged_obs_buf = None
        if self.vec_root_tensor.shape[1] > 1:
            # env assets states
            self.env_asset_root_states = self.vec_root_tensor[:, 1:1+self.num_assets, :]
            if self.get_privileged_obs:
                self.privileged_obs_buf = self.env_asset_root_states
            # env boundaries states
            self.env_boundary_root_states = self.vec_root_tensor[:, -env_boundary_count:, :]

        self.gym.refresh_actor_root_state_tensor(self.sim)

        self.initial_root_states = self.root_states.clone()
        self.counter = 0

        # controller
        self.cmd_thrusts = torch.zeros((self.num_envs, 4))
        # choice 1 from rate ctrl and vel ctrl
        if(cfg.env.ctl_mode == "pos"):
            self.action_upper_limits = torch.tensor(
            [3, 3, 3, 6.0], device=self.device, dtype=torch.float32)
            self.action_lower_limits = torch.tensor(
            [-3, -3, -3, -6.0], device=self.device, dtype=torch.float32)
            self.parallel_pos_control = ParallelPosControl(self.num_envs)
        elif(cfg.env.ctl_mode == "vel"):
            self.action_upper_limits = torch.tensor(
                [6, 6, 6, 6], device=self.device, dtype=torch.float32)
            self.action_lower_limits = torch.tensor(
                [-6, -6, -6, -6], device=self.device, dtype=torch.float32)
            self.parallel_vel_control = ParallelVelControl(self.num_envs)
        elif(cfg.env.ctl_mode == "atti"): # w, x, y, z, thrust
            self.action_upper_limits = torch.tensor(
            [1, 1, 1, 1, 1], device=self.device, dtype=torch.float32)
            self.action_lower_limits = torch.tensor(
            [-1, -1, -1, -1, 0.], device=self.device, dtype=torch.float32)
            self.parallel_atti_control = ParallelAttiControl(self.num_envs)
        elif(cfg.env.ctl_mode == "rate"):
            self.action_upper_limits = torch.tensor(
                [1, 1, 1, 1], device=self.device, dtype=torch.float32)
            self.action_lower_limits = torch.tensor(
                [-1, -1, -1, 0], device=self.device, dtype=torch.float32)
            self.parallel_rate_control = ParallelRateControl(self.num_envs)
        elif(cfg.env.ctl_mode == "prop"):
            self.action_upper_limits = torch.tensor(
                [1, 1, 1, 1], device=self.device, dtype=torch.float32)
            self.action_lower_limits = torch.tensor(
                [0, 0, 0, 0], device=self.device, dtype=torch.float32)
        else:
            print("Mode Error!")

        self.forces = torch.zeros((self.num_envs, bodies_per_env, 3),
                                  dtype=torch.float32, device=self.device, requires_grad=False)
        self.torques = torch.zeros((self.num_envs, bodies_per_env, 3),
                                   dtype=torch.float32, device=self.device, requires_grad=False)
        
        # control parameters
        self.thrusts = torch.zeros((self.num_envs, 4, 3), dtype=torch.float32, device=self.device)

        # set target states
        self.target_states = torch.tensor(self.cfg.env.target_state, device=self.device).repeat(self.num_envs, 1)

        # actions
        self.actions = torch.zeros((self.num_envs, self.num_actions), device=self.device)
        self.pre_actions = torch.zeros((self.num_envs, self.num_actions), device=self.device)

        self.contact_forces = gymtorch.wrap_tensor(self.contact_force_tensor).view(self.num_envs, bodies_per_env, 3)[:, 0]
        self.collisions = torch.zeros(self.num_envs, device=self.device)

        if self.enable_onboard_cameras:
            print("Onboard cameras enabled...")
            print("camera resolution =========== ", self.cam_resolution)
            self.full_camera_array = torch.zeros((self.num_envs, self.cam_channel, self.cam_resolution[0], self.cam_resolution[1]), device=self.device) # 1 for depth

        if self.viewer:
            cam_pos_x, cam_pos_y, cam_pos_z = self.cfg.viewer.pos[0], self.cfg.viewer.pos[1], self.cfg.viewer.pos[2]
            cam_target_x, cam_target_y, cam_target_z = self.cfg.viewer.lookat[0], self.cfg.viewer.lookat[1], self.cfg.viewer.lookat[2]
            cam_pos = gymapi.Vec3(cam_pos_x, cam_pos_y, cam_pos_z)
            cam_target = gymapi.Vec3(cam_target_x, cam_target_y, cam_target_z)
            cam_ref_env = self.cfg.viewer.ref_env
            
            self.gym.viewer_camera_look_at(self.viewer, None, cam_pos, cam_target)

    def create_sim(self):
        self.sim = self.gym.create_sim(
            self.sim_device_id, self.graphics_device_id, self.physics_engine, self.sim_params)
        if self.cfg.env.create_ground_plane:
            self._create_ground_plane()
        self._create_envs()
        self.progress_buf = torch.zeros(
            self.cfg.env.num_envs, device=self.sim_device, dtype=torch.long)

    def _create_ground_plane(self):
        plane_params = gymapi.PlaneParams()
        plane_params.normal = gymapi.Vec3(0.0, 0.0, 1.0)
        self.gym.add_ground(self.sim, plane_params)
        return

    def _create_envs(self):
        print("\n\n\n\n\n CREATING ENVIRONMENT \n\n\n\n\n\n")
        start_pose = gymapi.Transform()
        pos = torch.tensor([0, 0, 0], device=self.device)
        start_pose.p = gymapi.Vec3(*pos)
        self.env_spacing = self.cfg.env.env_spacing
        env_lower = gymapi.Vec3(-self.env_spacing, - self.env_spacing, -self.env_spacing)
        env_upper = gymapi.Vec3(self.env_spacing, self.env_spacing, self.env_spacing)
        
        self.actor_handles = []
        self.env_asset_handles = []
        self.envs = []
        self.camera_handles = []
        self.camera_tensors = []

        # load robots and assets
        self.asset_manager.load_asset(self.gym, self.sim)
        
        for i in range(self.num_envs):
            # create environment
            env_handle = self.gym.create_env(self.sim, env_lower, env_upper, int(np.sqrt(self.num_envs)))
            self.envs.append(env_handle)
            
            actor_handles, camera_handles, camera_tensors, env_asset_handles = \
                self.asset_manager.create_asset(env_handle, start_pose, i)
            
            # add all envs handles together
            self.actor_handles += actor_handles
            self.camera_handles += camera_handles
            self.camera_tensors += camera_tensors
            self.env_asset_handles += env_asset_handles

        self.enable_onboard_cameras = False if not camera_handles else True
        if self.enable_onboard_cameras:
            assert len(camera_tensors) != 0
            if camera_tensors[0].dim() == 2:
                h, w = camera_tensors[0].size()
                self.cam_resolution = (w, h)
                self.cam_channel = 1
            else:
                c, h, w = camera_tensors[0].size()
                self.cam_resolution = (w, h)
                self.cam_channel = c

        print("\n\n\n\n\n ENVIRONMENT CREATED \n\n\n\n\n\n")

    def pre_physics_step(self, _actions):
        # if self.counter % 250 == 0:
        #     print("self.counter:", self.counter)
        self.counter += 1

        reset_env_ids = self.reset_buf.nonzero(as_tuple=False).squeeze(-1)
        if len(reset_env_ids) > 0:
            self.reset_idx(reset_env_ids)
        self.actions = _actions.to(self.device) # [-1, 1]
        
        actions = self.actions
        if self.ctl_mode == 'rate' or self.ctl_mode == 'atti': 
            actions[..., -1] = 0.5 + 0.5 * self.actions[..., -1]
        # print("actions:", actions[0])
        actions = tensor_clamp(actions, self.action_lower_limits, self.action_upper_limits)
        
        actions_cpu = actions.cpu().numpy()
        
        #--------------- input state for pid controller. tensor [n,4] --------#
        obs_buf_cpu = self.root_states.cpu().numpy()
        # pos
        root_pos_cpu = self.root_states[..., 0:3].cpu().numpy()
        # quat. if w is negative, then set it to positive. x,y,z,w
        self.root_states[..., 3:7] = torch.where(self.root_states[..., 6:7] < 0, 
                                                 -self.root_states[..., 3:7], 
                                                 self.root_states[..., 3:7])
        root_quats_cpu = self.root_states[..., 3:7].cpu().numpy() # x,y,z,w
        # lin vel
        lin_vel_cpu = self.root_states[..., 7:10].cpu().numpy()
        # ang vel
        ang_vel_cpu = self.root_states[..., 10:13].cpu().numpy()

        # print(actions)
        control_mode_ = self.ctl_mode
        if(control_mode_ == "pos"):
            root_quats_cpu = root_quats_cpu[:, [3, 0, 1, 2]]
            self.parallel_pos_control.set_status(root_pos_cpu,root_quats_cpu,lin_vel_cpu,ang_vel_cpu,0.01)
            self.cmd_thrusts = torch.tensor(self.parallel_pos_control.update(actions_cpu.astype(np.float64)))
        elif(control_mode_ == "vel"):
            root_quats_cpu = root_quats_cpu[:, [3, 0, 1, 2]]
            self.parallel_vel_control.set_status(root_pos_cpu,root_quats_cpu,lin_vel_cpu,ang_vel_cpu,0.01)
            self.cmd_thrusts = torch.tensor(self.parallel_vel_control.update(actions_cpu.astype(np.float64)))
        elif(control_mode_ == "atti"):
            root_quats_cpu = root_quats_cpu[:, [3, 0, 1, 2]] # w, x, y, z
            self.parallel_atti_control.set_status(root_pos_cpu,root_quats_cpu,lin_vel_cpu,ang_vel_cpu,0.01)
            self.cmd_thrusts = torch.tensor(self.parallel_atti_control.update(actions_cpu.astype(np.float64))) 
        elif(control_mode_ == "rate"):
            root_quats_cpu = root_quats_cpu[:, [3, 0, 1, 2]]
            self.parallel_rate_control.set_q_world(root_quats_cpu.astype(np.float64))
            # print("thrust", actions_cpu[0][-1])
            self.cmd_thrusts = torch.tensor(self.parallel_rate_control.update(actions_cpu.astype(np.float64),ang_vel_cpu.astype(np.float64),0.01)) 
            # print("thrust on prop", self.cmd_thrusts[0])
        elif(control_mode_ == "prop"):
            self.cmd_thrusts =  actions
        else:
            print("Mode error")

        delta = .0*torch_rand_float(-1.0, 1.0, (self.num_envs, 1), device=self.device).repeat(1,4) + 9.59 
        thrusts=(self.cmd_thrusts.to(self.device) *delta)

        force_x = torch.zeros(self.num_envs, 4, dtype=torch.float32, device=self.device)
        force_y = torch.zeros(self.num_envs, 4, dtype=torch.float32, device=self.device)
        force_xy = torch.cat((force_x, force_y), 1).reshape(-1, 4, 2)
        thrusts = thrusts.reshape(-1, 4, 1)
        thrusts = torch.cat((force_xy, thrusts), 2)

        self.thrusts = thrusts

        # # clear actions for reset envs
        self.thrusts[reset_env_ids] = 0
        # # spin spinning rotors
        prop_rot = ((self.cmd_thrusts)*0.2).to(self.device)

        self.torques[:, 1, 2] = -prop_rot[:, 0]
        self.torques[:, 2, 2] = -prop_rot[:, 1]
        self.torques[:, 3, 2] = prop_rot[:, 2]
        self.torques[:, 4, 2] = prop_rot[:, 3]

        self.forces[:, 1:5] = self.thrusts

        # apply actions
        self.gym.apply_rigid_body_force_tensors(self.sim, gymtorch.unwrap_tensor(
            self.forces), gymtorch.unwrap_tensor(self.torques), gymapi.LOCAL_SPACE)
        # self.gym.apply_rigid_body_force_tensors(self.sim, gymtorch.unwrap_tensor(
        #     self.forces), gymtorch.unwrap_tensor(self.torques), gymapi.GLOBAL_SPACE)
        # apply propeller rotation
        # self.gym.set_joint_target_velocity(self.sim, )

    def post_physics_step(self):
        self.gym.refresh_actor_root_state_tensor(self.sim)
        self.gym.refresh_net_contact_force_tensor(self.sim)

    def step(self, actions):
        # step physics and render each frame
        for i in range(self.cfg.env.num_control_steps_per_env_step):
            self.pre_physics_step(actions)
            self.gym.simulate(self.sim)
            # NOTE: as per the isaacgym docs, self.gym.fetch_results must be called after self.gym.simulate, but not having it here seems to work fine
            # it is called in the render function.
            self.post_physics_step()
        
        self.render(sync_frame_time=False)
        rate = self.cfg.env.cam_dt / self.cfg.sim.dt
        if self.counter % rate == 0:
            if self.enable_onboard_cameras:
                self.render_cameras()

        self.progress_buf += 1
        self.check_collisions()
        self.compute_observations()
        self.compute_reward()

        if self.cfg.env.reset_on_collision:
            ones = torch.ones_like(self.reset_buf)
            self.reset_buf = torch.where(self.collisions > 0, ones, self.reset_buf)

        reset_env_ids = self.reset_buf.nonzero(as_tuple=False).squeeze(-1)
        if len(reset_env_ids) > 0:
            self.reset_idx(reset_env_ids)

        self.time_out_buf = self.progress_buf > self.max_episode_length
        self.extras["time_outs"] = self.time_out_buf
        self.extras["item_reward_info"] = self.item_reward_info

        obs = {
            'image': self.full_camera_array,
            'observation': self.obs_buf,
        }
        return obs, self.privileged_obs_buf, self.rew_buf, self.reset_buf, self.extras

    def reset_idx(self, env_ids):
        num_resets = len(env_ids)

        # set env boundaries
        self.env_boundary_root_states[env_ids, 0, :] = 0
        self.env_boundary_root_states[env_ids, 0, 2:3] = 0.02
        self.env_boundary_root_states[env_ids, 0, 6:7] = 1

        # randomize env asset root states
        self.env_asset_root_states[env_ids, :, 0:1] = LENGTH * torch_rand_float(-1.0, 1.0, (num_resets, self.num_assets, 1), self.device) + torch.tensor([0.], device=self.device)
        self.env_asset_root_states[env_ids, :, 1:2] = WIDTH * torch_rand_float(-1.0, 1.0, (num_resets, self.num_assets, 1), self.device) + torch.tensor([0.], device=self.device)
        self.env_asset_root_states[env_ids, :, 2:3] = 0
        assets_root_angle = torch.concatenate([0 * torch_rand_float(-torch.pi, torch.pi, (num_resets, self.num_assets, 2), self.device),
                                       torch_rand_float(-torch.pi, torch.pi, (num_resets, self.num_assets, 1), self.device)], dim=-1)
        assets_matrix = T.euler_angles_to_matrix(assets_root_angle, 'XYZ')
        assets_root_quats = T.matrix_to_quaternion(assets_matrix)
        self.env_asset_root_states[env_ids, :, 3:7] = assets_root_quats[:, :, [1, 2, 3, 0]]

        # randomize root states
        self.root_states[env_ids, 0:2] = torch.tensor([-LENGTH-0.5, 0.], device=self.device)
        self.root_states[env_ids, 2:3] = .0 *torch_rand_float(-1., 1., (num_resets, 1), self.device) + FLY_HEIGHT

        # randomize root orientation
        root_angle = torch.concatenate([0.01*torch_rand_float(-torch.pi, torch.pi, (num_resets, 2), self.device), 
                                       0.05*torch_rand_float(-torch.pi, torch.pi, (num_resets, 1), self.device)], dim=-1)

        matrix = T.euler_angles_to_matrix(root_angle, 'XYZ')
        root_quats = T.matrix_to_quaternion(matrix) # w,x,y,z
        self.root_states[env_ids, 3:7] = root_quats[:, [1, 2, 3, 0]] #x,y,z,w

        # randomize root linear and angular velocities
        self.root_states[env_ids, 7:10] = 0.*torch_rand_float(-1.0, 1.0, (num_resets, 3), self.device)
        self.root_states[env_ids, 10:13] = 0.*torch_rand_float(-1.0, 1.0, (num_resets, 3), self.device)

        self.gym.set_actor_root_state_tensor(self.sim, self.root_tensor)
        self.progress_buf[env_ids] = 0
        self.reset_buf[env_ids] = 1

        self.pre_actions[env_ids] = 0
        
    def render_cameras(self):
        self.gym.render_all_camera_sensors(self.sim)
        self.gym.start_access_image_tensors(self.sim)
        self.dump_images()
        self.gym.end_access_image_tensors(self.sim)
        return
    
    def check_collisions(self):
        ones = torch.ones((self.num_envs), device=self.device)
        zeros = torch.zeros((self.num_envs), device=self.device)
        self.collisions[:] = 0
        self.collisions = torch.where(torch.norm(self.contact_forces, dim=-1) > 0.1, ones, zeros)

    def dump_images(self):
        for env_id in range(self.num_envs):
            # the depth values are in -ve z axis, so we need to flip it to positive
            self.full_camera_array[env_id, :] = -self.camera_tensors[env_id].T
            self.full_camera_array[env_id, :] = torch.where(self.full_camera_array[env_id, :] > 4.5, torch.tensor(4.5), self.full_camera_array[env_id, :])
            self.full_camera_array[env_id, :] = torch.clamp(self.full_camera_array[env_id, :], 0, 4.5) / 4.5

            def add_gaussian_noise(depth_map, mean=0.0, std=.1):
                noise = torch.normal(mean, std, size=depth_map.shape, device=depth_map.device)
                noisy_depth_map = depth_map + noise
                return torch.clamp(noisy_depth_map, 0.0, depth_map.max())
            
            def add_multiplicative_noise(depth_map, mean=1.0, std=0.3):
                noise = torch.normal(mean, std, size=depth_map.shape, device=depth_map.device)
                noisy_depth_map = depth_map * noise
                return torch.clamp(noisy_depth_map, 0.0, depth_map.max())
            
            def apply_gaussian_blur(depth_map, kernel_size=5, sigma=1.0):
                # Create a Gaussian kernel
                kernel = torch.randint(0, 256, (kernel_size, kernel_size), dtype=torch.float32) / 256.0
                kernel = kernel.unsqueeze(0).unsqueeze(0)  # Add batch and channel dimensions
                kernel = kernel.to(depth_map.device)

                # Apply convolution for Gaussian blur
                return F.conv2d(depth_map.unsqueeze(0), kernel, padding=kernel_size//2).squeeze(0)
            
            # self.full_camera_array[env_id, :] = add_gaussian_noise(self.full_camera_array[env_id, :])
            # self.full_camera_array[env_id, :] = add_multiplicative_noise(self.full_camera_array[env_id, :])
            # self.full_camera_array[env_id, :] = apply_gaussian_blur(self.full_camera_array[env_id, :])

            depth_image = self.full_camera_array[env_id, :].T.cpu().numpy()
            dist = cv2.normalize(depth_image, None, 0,255, cv2.NORM_MINMAX, cv2.CV_8UC1)
            depth_colored = cv2.applyColorMap(dist, cv2.COLORMAP_PLASMA)
            # depth_colored = cv2.applyColorMap(dist, cv2.COLORMAP_JET)

            # cv2.imshow(str(env_id), depth_colored)
            # cv2.waitKey(1)
    
    def compute_observations(self):
        self.root_matrix = T.quaternion_to_matrix(self.root_quats[:, [3, 0, 1, 2]]).reshape(self.num_envs, 9)
        # print(self.root_matrix)
        self.obs_buf[..., 0:9] = self.root_matrix
        self.obs_buf[..., 9:12] = self.root_positions
        self.obs_buf[..., 12:15] = self.root_linvels
        self.obs_buf[..., 15:18] = self.root_angvels

        self.add_noise()

        self.obs_buf -= self.target_states

        return self.obs_buf
    
    def add_noise(self):
        matrix_noise = 1e-3 *torch_normal_float((self.num_envs, 9), self.device)
        pos_noise = 5e-3 *torch_normal_float((self.num_envs, 3), self.device)
        linvels_noise = 2e-2 *torch_normal_float((self.num_envs, 3), self.device)
        angvels_noise = 4e-1 *torch_normal_float((self.num_envs, 3), self.device)

        self.obs_buf[..., 0:9] += matrix_noise
        self.obs_buf[..., 9:12] += pos_noise
        self.obs_buf[..., 12:15] += linvels_noise
        self.obs_buf[..., 15:18] += angvels_noise
    
    def compute_reward(self):
        self.rew_buf[:], self.reset_buf[:] ,self.item_reward_info= self.compute_quadcopter_reward()
        # update prev 
        self.pre_actions = self.actions.clone()

    def compute_quadcopter_reward(self):
        # reward
        reward = 0
        # resets
        ones = torch.ones_like(self.reset_buf)
        die = torch.zeros_like(self.reset_buf)
        reset = torch.where(self.progress_buf >= self.max_episode_length - 1, ones, die)
        # record
        item_reward_info = {}

        return reward, reset, item_reward_info
    
###=========================jit functions=========================###
#####################################################################

@torch.jit.script
def quat_rotate(q, v):
    shape = q.shape
    q_w = q[:, -1]
    q_vec = q[:, :3]
    a = v * (2.0 * q_w ** 2 - 1.0).unsqueeze(-1)
    b = torch.cross(q_vec, v, dim=-1) * q_w.unsqueeze(-1) * 2.0
    c = q_vec * \
        torch.bmm(q_vec.view(shape[0], 1, 3), v.view(
            shape[0], 3, 1)).squeeze(-1) * 2.0
    return a + b + c

@torch.jit.script
def quat_axis(q, axis=0):
    # type: (Tensor, int) -> Tensor
    basis_vec = torch.zeros(q.shape[0], 3, device=q.device)
    basis_vec[:, axis] = 1
    return quat_rotate(q, basis_vec)

@torch.jit.script
def torch_normal_float(shape, device):
    # type: (Tuple[int, int], str) -> Tensor
    return torch.randn(*shape, device=device)