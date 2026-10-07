"""Stage 5.1: load GVHMR's SMPL-X parameters and rebuild the body joints (GDD §4 stage 5).

GVHMR writes `hmr4d_results.pt`, a torch dict. We read only `smpl_params_global` (world frame).
The demo resamples every input video to 30 fps before inference (GVHMR is a 30 fps model), so the
parameters are always at 30 fps, whatever the source video's rate: a 124-frame 24 fps take comes
back as 155 frames.

Joint positions come from the SMPL-X body model (registration-gated, outside git; M0.3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GVHMR_FPS = 30.0
NUM_BODY_JOINTS = 22  # pelvis + 21 body joints; SMPL-X joints 22+ are jaw, eyes and fingers
NUM_BETAS = 10

# SMPL-X joint order for the first 22 joints (smplx.joint_names.JOINT_NAMES)
BODY_JOINT_NAMES = (
    "pelvis",
    "left_hip",
    "right_hip",
    "spine1",
    "left_knee",
    "right_knee",
    "spine2",
    "left_ankle",
    "right_ankle",
    "spine3",
    "left_foot",
    "right_foot",
    "neck",
    "left_collar",
    "right_collar",
    "head",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
)

DEFAULT_BODY_MODELS = Path.home() / "motion-ai-checkpoints" / "body_models"


@dataclass(frozen=True)
class GvhmrParams:
    """Per-frame SMPL-X parameters in GVHMR's world frame. Rotations are axis-angle."""

    global_orient: np.ndarray  # (T, 3) pelvis rotation
    body_pose: np.ndarray  # (T, 21, 3) joints 1..21, parent-relative
    transl: np.ndarray  # (T, 3) metres
    betas: np.ndarray  # (10,) shape, constant over the clip
    fps: float

    @property
    def num_frames(self) -> int:
        return self.global_orient.shape[0]


@dataclass(frozen=True)
class RestSkeleton:
    """The 22 body joints of one SMPL-X body shape in rest pose."""

    joints: np.ndarray  # (22, 3) rest positions, metres, in the model frame
    parents: np.ndarray  # (22,) parent index per joint, -1 for the pelvis
    sole_y: float = 0.0  # height of the lowest mesh vertex (the soles) in rest pose
    names: tuple[str, ...] = BODY_JOINT_NAMES

    def offsets(self) -> np.ndarray:
        """(22, 3) bone offsets from each joint's parent; the pelvis keeps its rest position."""
        out = self.joints.copy()
        out[1:] -= self.joints[self.parents[1:]]
        return out


def load_gvhmr(path: Path) -> GvhmrParams:
    """Read `smpl_params_global` from a GVHMR `hmr4d_results.pt`."""
    import torch

    data = torch.load(Path(path), map_location="cpu", weights_only=False)
    if "smpl_params_global" not in data:
        raise ValueError(f"{path}: no smpl_params_global (keys: {sorted(data)})")
    params = data["smpl_params_global"]
    p = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in params.items()}

    global_orient, body_pose, transl, betas = (
        p["global_orient"],
        p["body_pose"],
        p["transl"],
        p["betas"],
    )
    n = global_orient.shape[0]
    if global_orient.shape != (n, 3) or body_pose.shape != (n, 63) or transl.shape != (n, 3):
        raise ValueError(
            f"{path}: unexpected shapes global_orient {global_orient.shape}, "
            f"body_pose {body_pose.shape}, transl {transl.shape}"
        )
    # GVHMR stores the same betas on every frame; average in case a future version does not
    if betas.ndim == 2:
        betas = betas.mean(axis=0)
    return GvhmrParams(
        global_orient=global_orient,
        body_pose=body_pose.reshape(n, 21, 3),
        transl=transl,
        betas=betas[:NUM_BETAS],
        fps=GVHMR_FPS,
    )


def body_models_dir() -> Path:
    """`GVHMR_BODY_MODELS` (shared with the worker), else `~/motion-ai-checkpoints/body_models`."""
    env = os.environ.get("GVHMR_BODY_MODELS")
    return Path(env).expanduser() if env else DEFAULT_BODY_MODELS


def rest_skeleton(
    betas: np.ndarray, body_models: Path | None = None, gender: str = "neutral"
) -> RestSkeleton:
    """Rebuild the 22 body joint rest positions and the parent table from `betas` with `smplx`.

    `body_models` is the directory holding `smplx/SMPLX_NEUTRAL.npz` (default `body_models_dir()`).
    GVHMR fits the neutral model with 10 betas.
    """
    import smplx
    import torch

    root = Path(body_models) if body_models is not None else body_models_dir()
    model_file = root / "smplx" / f"SMPLX_{gender.upper()}.npz"
    if not model_file.is_file():
        raise FileNotFoundError(
            f"SMPL-X body model not found: {model_file} (see docs/checkpoints.md)"
        )

    model = smplx.create(
        str(root),
        model_type="smplx",
        gender=gender,
        num_betas=NUM_BETAS,
        use_pca=False,
        flat_hand_mean=True,
        ext="npz",
    )
    with torch.no_grad():
        out = model(betas=torch.as_tensor(betas, dtype=torch.float32).reshape(1, NUM_BETAS))
    joints = out.joints[0, :NUM_BODY_JOINTS].numpy().astype(np.float32)
    parents = model.parents[:NUM_BODY_JOINTS].numpy().astype(np.int64)
    parents[0] = -1
    sole_y = float(out.vertices[0, :, 1].min())
    return RestSkeleton(joints=joints, parents=parents, sole_y=sole_y)


# Stage 5.2: axis fix. GVHMR's world frame ("ay", gvhmr/utils/geo/hmr_global.py) is already Y-up,
# right-handed and in metres: up is minus gravity, +Z is the camera's viewing direction on frame 0
# projected onto the ground, +X is camera-left. glTF is Y-up, right-handed, metres, with the asset's
# front at +Z. Turning 180 degrees about Y makes "towards the camera" the glTF front, so a camera at
# +Z looking down -Z (Camera3D's default direction) frames the clip as the video does.
# See docs/pipeline-notes.md.
GVHMR_TO_GLTF = np.diag([-1.0, 1.0, -1.0]).astype(np.float32)


def axis_angle_to_matrix(aa: np.ndarray) -> np.ndarray:
    """(..., 3) axis-angle to (..., 3, 3) rotation matrices (Rodrigues)."""
    aa = np.asarray(aa, dtype=np.float64)
    angle = np.linalg.norm(aa, axis=-1, keepdims=True)
    axis = np.divide(aa, angle, out=np.zeros_like(aa), where=angle > 1e-12)
    x, y, z = axis[..., 0], axis[..., 1], axis[..., 2]
    zero = np.zeros_like(x)
    k = np.stack([zero, -z, y, z, zero, -x, -y, x, zero], axis=-1).reshape(*aa.shape[:-1], 3, 3)
    s, c = np.sin(angle)[..., None], np.cos(angle)[..., None]
    return np.eye(3) + s * k + (1.0 - c) * (k @ k)


def matrix_to_axis_angle(m: np.ndarray) -> np.ndarray:
    """(..., 3, 3) rotation matrices to (..., 3) axis-angle, angle in [0, pi]."""
    m = np.asarray(m, dtype=np.float64)
    cos = np.clip((np.trace(m, axis1=-2, axis2=-1) - 1.0) / 2.0, -1.0, 1.0)
    angle = np.arccos(cos)
    vee = np.stack(
        [m[..., 2, 1] - m[..., 1, 2], m[..., 0, 2] - m[..., 2, 0], m[..., 1, 0] - m[..., 0, 1]],
        axis=-1,
    )
    sin = np.sin(angle)
    out = np.where(
        (sin > 1e-6)[..., None],
        vee / (2.0 * np.maximum(sin, 1e-12))[..., None] * angle[..., None],
        0.0,
    )
    # near pi the vee vector vanishes: take the axis from the symmetric part instead
    near_pi = angle > np.pi - 1e-3
    if np.any(near_pi):
        mp = m[near_pi]
        # symmetric part minus cos * I is (1 - cos) * axis axis^T; its largest column is the axis
        outer = (mp + np.swapaxes(mp, -1, -2)) / 2.0 - cos[near_pi][..., None, None] * np.eye(3)
        col = np.argmax(np.diagonal(outer, axis1=-2, axis2=-1), axis=-1)
        axis = outer[np.arange(len(col)), :, col]
        axis /= np.linalg.norm(axis, axis=-1, keepdims=True)
        # fix the sign so the result agrees with the (small) antisymmetric part when there is one
        sign = np.where((axis * vee[near_pi]).sum(-1) < 0, -1.0, 1.0)[..., None]
        out[near_pi] = axis * sign * angle[near_pi][..., None]
    return out


def to_gltf_frame(
    positions: np.ndarray, global_orient: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray | None]:
    """Convert world-frame data from GVHMR's frame to glTF's (Y-up, right-handed, metres, front +Z).

    `positions` (..., 3) are world points: joint positions or the pelvis track. Do not pass SMPL-X
    `transl`, which is an offset applied before the pelvis rest position and does not rotate like a
    point. `global_orient` (..., 3) is the pelvis world rotation, axis-angle. Parent-relative
    rotations (`body_pose`) do not depend on the world frame and need no conversion.
    """
    r = GVHMR_TO_GLTF.astype(np.float64)
    pos = np.asarray(positions)
    out_pos = (pos.astype(np.float64) @ r.T).astype(pos.dtype)
    if global_orient is None:
        return out_pos, None
    go = np.asarray(global_orient)
    out_rot = matrix_to_axis_angle(r @ axis_angle_to_matrix(go)).astype(go.dtype)
    return out_pos, out_rot
