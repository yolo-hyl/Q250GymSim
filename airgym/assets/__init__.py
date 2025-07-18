from airgym.assets import asset_register
from airgym import AIRGYM_ROOT_DIR
import numpy as np

THIN_SEMANTIC_ID = 1
VTREE_SEMANTIC_ID = 2
OBJECT_SEMANTIC_ID = 3
CUBE_SEMANTIC_ID = 4
FLAG_SEMANTIC_ID = 5
TREE_SEMANTIC_ID = 6
BALL_SEMENTIC_ID = 7
GROUND_SEMANTIC_ID = 8

registry = asset_register.AssetRegistry()

registry.register_asset(
    "X152b",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/robots/X152b/model.urdf",
        "name": "X152b",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": False,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
    },
    asset_type="single"
)

registry.register_asset(
    "Q250",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/robots/Q250/model.urdf",
        "name": "Q250",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": False,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
    },
    asset_type="single"
)

registry.register_asset(
    "iris",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/robots/iris/model.urdf",
        "name": "iris",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": False,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
    },
    asset_type="single"
)

registry.register_asset(
    "thin",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/thin",
        "name": "thin",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 10,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": THIN_SEMANTIC_ID,
        "color": [170,66,66],
        "vhacd_enabled": False,
    },
    asset_type="group"
)

registry.register_asset(
    "trees",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/trees",
        "name": "trees",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 10,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": TREE_SEMANTIC_ID,
        "vhacd_enabled": False,
    },
    asset_type="group"
)

registry.register_asset(
    "vtrees",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/vtrees",
        "name": "vtrees",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 10,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": VTREE_SEMANTIC_ID,
        "color": [70,200,100],
        "vhacd_enabled": False,
    },
    asset_type="group"
)

registry.register_asset(
    "objects",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/objects",
        "name": "objects",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 10,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": OBJECT_SEMANTIC_ID,
        "color": [70,200,100],
        "vhacd_enabled": False,
    },
    asset_type="group"
)

registry.register_asset(
    "cubes",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/cubes",
        "name": "cubes",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 10,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": CUBE_SEMANTIC_ID,
        "vhacd_enabled": True,
        "vhacd_enabled.resolution": 500000,
    },
    asset_type="group"
)

registry.register_asset(
    "balls",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/balls",
        "name": "balls",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": True,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 10,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": BALL_SEMENTIC_ID,
        "color": [70,200,100],
        "vhacd_enabled": False,
        "vhacd_enabled.resolution": 500000,
    },
    asset_type="group"
)

registry.register_asset(
    "flags",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/flags",
        "name": "flags",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": False,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 10,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": FLAG_SEMANTIC_ID,
        "vhacd_enabled": True,
        "vhacd_enabled.resolution": 500000,
    },
    asset_type="group"
)

registry.register_asset(
    "8x18ground",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/grounds/8x18ground/model.urdf",
        "name": "8x18ground",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": True,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 1,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": GROUND_SEMANTIC_ID,
        "vhacd_enabled": False,
    },
    asset_type="single"
)

registry.register_asset(
    "18x18ground",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/grounds/18x18ground/model.urdf",
        "name": "18x18ground",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": True,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 1,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": GROUND_SEMANTIC_ID,
        "vhacd_enabled": False,
    },
    asset_type="single"
)

registry.register_asset(
    "18x18o",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/grounds/18x18o/model.urdf",
        "name": "18x18o",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": True,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 1,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": GROUND_SEMANTIC_ID,
        "vhacd_enabled": False,
    },
    asset_type="single"
)

registry.register_asset(
    "18x18s",
    override_params={
        "path": f"{AIRGYM_ROOT_DIR}/airgym/assets/env_assets/grounds/18x18s/model.urdf",
        "name": "18x18s",
        "base_link_name": "base_link",
        "foot_name": None,
        "penalize_contacts_on": [],
        "terminate_after_contacts_on": [],
        "disable_gravity": True,
        "collapse_fixed_joints": True,
        "fix_base_link": True,
        "collision_mask": 1,
        "density": -1,
        "angular_damping": 0.0,
        "linear_damping": 0.0,
        "replace_cylinder_with_capsule": False,
        "flip_visual_attachments": False,
        "max_angular_velocity": 100.,
        "max_linear_velocity": 100.,
        "armature": 0.001,
        "num_assets": 1,
        "links_per_asset": 1,
        "set_whole_body_semantic_mask": True,
        "semantic_id": GROUND_SEMANTIC_ID,
        "vhacd_enabled": False,
    },
    asset_type="single"
)