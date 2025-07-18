import numpy as np
import torch

from isaacgym import gymtorch, gymapi
from isaacgym.torch_utils import *
from airgym.envs.base.base_task import BaseTask
from airgym.envs.base.hovering_config import HoveringCfg
from airgym.assets.asset_manager import AssetManager

from rlPx4Controller.pyParallelControl import ParallelRateControl,ParallelVelControl,ParallelAttiControl,ParallelPosControl

import pytorch3d.transforms as T

# import rospy
# from std_msgs.msg import Float64MultiArray

def quaternion_conjugate(q: torch.Tensor):
    """Compute the conjugate of a quaternion."""
    q_conj = q.clone()
    q_conj[:, :3] = -q_conj[:, :3]
    return q_conj

def quaternion_multiply(q1: torch.Tensor, q2: torch.Tensor):
    """Multiply two quaternions."""
    x1, y1, z1, w1 = q1.unbind(-1)
    x2, y2, z2, w2 = q2.unbind(-1)
    x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
    y = w1 * y2 + y1 * w2 + z1 * x2 - x1 * z2
    z = w1 * z2 + z1 * w2 + x1 * y2 - y1 * x2
    w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
    return torch.stack((x, y, z, w), dim=-1)

def compute_yaw_diff(a: torch.Tensor, b: torch.Tensor):
    """Compute the difference between two sets of Euler angles. a & b in [-pi, pi]"""
    diff = b - a
    diff = torch.where(diff < -torch.pi, diff + 2*torch.pi, diff)
    diff = torch.where(diff > torch.pi, diff - 2*torch.pi, diff)
    return diff

class Hovering(BaseTask):

    def __init__(self, cfg: HoveringCfg, sim_params, physics_engine, sim_device, headless):
        
        assert cfg.env.ctl_mode is not None, "Please specify one control mode!"
        assert cfg.env.asset_model is not None, "Please specify one asset model!"
        assert cfg.asset_config.include_robot[cfg.env.asset_model] is not None, "Please append asset config in your task config!"
        import copy
        new_cfg = copy.deepcopy(cfg)
        new_cfg.asset_config.include_robot = {cfg.env.asset_model: cfg.asset_config.include_robot[cfg.env.asset_model]}
        self.cfg = new_cfg

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
            self.env_asset_root_states = self.vec_root_tensor[:, 1:, :]
            if self.get_privileged_obs:
                self.privileged_obs_buf = self.env_asset_root_states
                
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
                [6, 6, 6, 1], device=self.device, dtype=torch.float32)
            self.action_lower_limits = torch.tensor(
                [-6, -6, -6, 0], device=self.device, dtype=torch.float32)
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

        if self.viewer:
            cam_pos_x, cam_pos_y, cam_pos_z = self.cfg.viewer.pos[0], self.cfg.viewer.pos[1], self.cfg.viewer.pos[2]
            cam_target_x, cam_target_y, cam_target_z = self.cfg.viewer.lookat[0], self.cfg.viewer.lookat[1], self.cfg.viewer.lookat[2]
            cam_pos = gymapi.Vec3(cam_pos_x, cam_pos_y, cam_pos_z)
            cam_target = gymapi.Vec3(cam_target_x, cam_target_y, cam_target_z)
            cam_ref_env = self.cfg.viewer.ref_env
            
            self.gym.viewer_camera_look_at(self.viewer, None, cam_pos, cam_target)

        # test ros actions
        # rospy.init_node('ctl_onboard', anonymous=True)
        # self.pub = rospy.Publisher('/action', Float64MultiArray, queue_size=10)
        # self.sub = rospy.Subscriber('/target_state', Float64MultiArray, self.callback)

    def callback(self, data):
        self.target_state = torch.tensor(data.data, device=self.device)
        self.target_states = self.target_state.repeat(self.num_envs, 1)

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
        self.env_spacing = self.cfg.env.env_spacing
        env_lower = gymapi.Vec3(-self.env_spacing, -
                                self.env_spacing, -self.env_spacing)
        env_upper = gymapi.Vec3(
            self.env_spacing, self.env_spacing, self.env_spacing)
        
        self.actor_handles = []
        self.env_asset_handles = []
        self.envs = []

        # load robots and assets
        self.asset_manager.load_asset(self.gym, self.sim)

        for i in range(self.num_envs):
            # create environment
            env_handle = self.gym.create_env(self.sim, env_lower, env_upper, int(np.sqrt(self.num_envs)))
            self.envs.append(env_handle)
            
            actor_handles, _, _, env_asset_handles = \
                self.asset_manager.create_asset(env_handle, start_pose, i)
            
            # add all envs handles together
            self.actor_handles += actor_handles
            self.env_asset_handles += env_asset_handles

        print("\n\n\n\n\n ENVIRONMENT CREATED \n\n\n\n\n\n")

    def pre_physics_step(self, _actions):
        # resets
        if self.counter % 250 == 0:
            print("self.counter:", self.counter)
        self.counter += 1

        reset_env_ids = self.reset_buf.nonzero(as_tuple=False).squeeze(-1)
        if len(reset_env_ids) > 0:
            self.reset_idx(reset_env_ids)
        self.actions = _actions.to(self.device)
        
        if self.ctl_mode == 'rate' or self.ctl_mode == 'atti': 
            self.actions[..., -1] = 0.5 + 0.5 * self.actions[..., -1]
        self.actions = tensor_clamp(self.actions, self.action_lower_limits, self.action_upper_limits)
        actions_cpu = self.actions.cpu().numpy()
        
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
            self.cmd_thrusts = torch.tensor(self.parallel_rate_control.update(actions_cpu.astype(np.float64),ang_vel_cpu.astype(np.float64),0.01)) 
        elif(control_mode_ == "prop"):
            self.cmd_thrusts =  self.actions
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

    def post_physics_step(self):
        self.gym.refresh_actor_root_state_tensor(self.sim)

    def step(self, actions):
        # step physics and render each frame
        for i in range(self.cfg.env.num_control_steps_per_env_step):
            self.pre_physics_step(actions)
            self.gym.simulate(self.sim)
            # NOTE: as per the isaacgym docs, self.gym.fetch_results must be called after self.gym.simulate, but not having it here seems to work fine
            # it is called in the render function.
            self.post_physics_step()

        self.render(sync_frame_time=True)
        
        self.progress_buf += 1
        self.compute_observations()
        self.compute_reward()
        reset_env_ids = self.reset_buf.nonzero(as_tuple=False).squeeze(-1)
        if len(reset_env_ids) > 0:
            self.reset_idx(reset_env_ids)

        self.time_out_buf = self.progress_buf > self.max_episode_length
        self.extras["time_outs"] = self.time_out_buf
        self.extras["item_reward_info"] = self.item_reward_info
        
        return self.obs_buf, self.privileged_obs_buf, self.rew_buf, self.reset_buf, self.extras

    def reset_idx(self, env_ids):
        num_resets = len(env_ids)

        self.root_states[env_ids] = self.initial_root_states[env_ids]

        # randomize root states
        self.root_states[env_ids, 0:2] = torch_rand_float(-1.0, 1.0, (num_resets, 2), self.device) # .2
        self.root_states[env_ids, 2:3] = torch_rand_float(-1., 1., (num_resets, 1), self.device) # .2

        # randomize root orientation
        root_angle = torch.concatenate([0.01*torch_rand_float(-torch.pi, torch.pi, (num_resets, 2), self.device), # .01
                                       0.05*torch_rand_float(-torch.pi, torch.pi, (num_resets, 1), self.device)], dim=-1) # 0.05

        matrix = T.euler_angles_to_matrix(root_angle, 'XYZ')
        root_quats = T.matrix_to_quaternion(matrix) # w,x,y,z
        self.root_states[env_ids, 3:7] = root_quats[:, [1, 2, 3, 0]] #x,y,z,w

        # randomize root linear and angular velocities
        self.root_states[env_ids, 7:10] = 0.5*torch_rand_float(-1.0, 1.0, (num_resets, 3), self.device) # 0.5
        self.root_states[env_ids, 10:13] = 0.2*torch_rand_float(-1.0, 1.0, (num_resets, 3), self.device) # 0.2

        self.gym.set_actor_root_state_tensor(self.sim, self.root_tensor)
        self.reset_buf[env_ids] = 1
        self.progress_buf[env_ids] = 0

        self.pre_actions[env_ids] = 0

    def compute_observations(self):
        self.root_matrix = T.quaternion_to_matrix(self.root_quats[:, [3, 0, 1, 2]]).reshape(self.num_envs, 9)
        self.obs_buf[..., 0:9] = self.root_matrix
        self.obs_buf[..., 9:12] = self.root_positions
        self.obs_buf[..., 12:15] = self.root_linvels
        self.obs_buf[..., 15:18] = self.root_angvels
        self.add_noise()

        self.obs_buf[..., 0:18] -= self.target_states
        
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
        # action_data = Float64MultiArray()
        # action_data.data = [self.actions[0,0].item(),self.actions[0,1].item(),self.actions[0,2].item(),self.actions[0,3].item()]
        
        # ros target pub
        # self.pub.publish(action_data)
        
        # update prev 
        self.pre_actions = self.actions.clone()

    def compute_quadcopter_reward(self):
        # effort reward
        thrust_cmds = torch.clamp(self.cmd_thrusts, min=0.0, max=1.0).to('cuda')
        effort_reward = .1 * (1 - thrust_cmds).sum(-1)/4

        # continous action
        action_diff = self.actions - self.pre_actions
        if self.ctl_mode == "pos" or self.ctl_mode == 'vel' or self.ctl_mode == 'prop':
            continous_action_reward =  .2 * torch.exp(-torch.norm(action_diff[..., :], dim=-1))
        else:
            continous_action_reward = .2 * torch.exp(-torch.norm(action_diff[..., :-1], dim=-1)) + .5 / (1.0 + torch.square(3 * action_diff[..., -1]))
            thrust = self.actions[..., -1] # this thrust is the force on vertical axis
            thrust_reward = .1 * (1-torch.abs(0.1533 - thrust))
            # print(thrust)

        # distance
        target_positions = self.target_states[..., 9:12]
        relative_positions = target_positions - self.root_positions
        pos_diff = torch.norm(relative_positions, dim=-1)
        pos_reward = .7 / (1.0 + torch.square(1.6 * pos_diff))

        # velocity direction
        tar_direction = relative_positions / torch.norm(relative_positions, dim=1, keepdim=True)
        vel_direction = self.root_linvels / torch.norm(self.root_linvels, dim=1, keepdim=True)
        dot_product = (tar_direction * vel_direction).sum(dim=1)
        angle_diff = torch.acos(dot_product.clamp(-1.0, 1.0)).abs()
        vel_direction_reward = .1 * torch.exp(-angle_diff / torch.pi)
        
        # yaw
        target_matrix = self.target_states[..., 0:9].reshape(self.num_envs, 3,3)
        target_euler = T.matrix_to_euler_angles(target_matrix, 'XYZ')
        root_matrix = T.quaternion_to_matrix(self.root_quats[:, [3, 0, 1, 2]])
        root_euler = T.matrix_to_euler_angles(root_matrix, convention='XYZ')
        yaw_diff = compute_yaw_diff(target_euler[..., 2], root_euler[..., 2]) / torch.pi
        yaw_reward = 1.0 / (1.0 + torch.square(3 * yaw_diff))

        spinnage = torch.square(self.root_angvels[:, -1])
        spin_reward = 1.0 / (1.0 + torch.square(3 * spinnage))

        # uprightness
        ups = quat_axis(self.root_quats, 2)
        ups_reward = torch.square((ups[..., 2] + 1) / 2)

        if self.ctl_mode == "pos" or self.ctl_mode == 'vel' or self.ctl_mode == 'prop':
            reward = (
                continous_action_reward
                + effort_reward
                + pos_reward
                + pos_reward*(vel_direction_reward + ups_reward + spin_reward + yaw_reward)
            )
        else:
            reward = (
                continous_action_reward
                + effort_reward
                + thrust_reward
                + pos_reward
                + pos_reward*(vel_direction_reward + ups_reward + spin_reward + yaw_reward)
            )

        # resets due to misbehavior
        ones = torch.ones_like(self.reset_buf)
        die = torch.zeros_like(self.reset_buf)

        # resets due to episode length
        reset = torch.where(self.progress_buf >= self.max_episode_length - 1, ones, die)

        reset = torch.where(torch.norm(relative_positions, dim=1) > 4, ones, reset)

        reset = torch.where(relative_positions[..., 2] < -2, ones, reset)
        reset = torch.where(relative_positions[..., 2] > 2, ones, reset)

        reset = torch.where(ups[..., 2] < 0.0, ones, reset) # orient_z 小于0 = 飞行器朝下了

        # resets due to a negative w in quaternions
        if self.ctl_mode == "atti":
            reset = torch.where(self.actions[..., 0] < 0, ones, reset)

        item_reward_info = {}
        item_reward_info["continous_action_reward"] = continous_action_reward
        item_reward_info["effort_reward"] = effort_reward
        item_reward_info["thrust_reward"] = thrust_reward if self.ctl_mode == "atti" or self.ctl_mode == 'rate' else 0
        item_reward_info["pos_reward"] = pos_reward
        item_reward_info["vel_direction_reward"] = vel_direction_reward
        item_reward_info["ups_reward"] = ups_reward
        item_reward_info["spin_reward"] = spin_reward
        item_reward_info["yaw_reward"] = yaw_reward
        item_reward_info["reward"] = reward

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