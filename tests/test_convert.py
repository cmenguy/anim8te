from pathlib import Path

import numpy as np
import pytest

from anim8te.convert import (
    BODY_JOINT_NAMES,
    GVHMR_FPS,
    GVHMR_TO_GLTF,
    NUM_BODY_JOINTS,
    axis_angle_to_matrix,
    body_models_dir,
    load_gvhmr,
    matrix_to_axis_angle,
    rest_skeleton,
    to_gltf_frame,
)

# first 10 frames of smpl_params_global from a real GVHMR run (walk-ur7zdb, 24 fps take)
FIXTURE = Path(__file__).parent / "fixtures" / "hmr4d_walk_10f.pt"

# SMPL / SMPL-X kinematic tree for the 22 body joints
SMPLX_BODY_PARENTS = [-1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19]

needs_body_model = pytest.mark.skipif(
    not (body_models_dir() / "smplx" / "SMPLX_NEUTRAL.npz").is_file(),
    reason="SMPL-X body model not installed (docs/checkpoints.md)",
)


def test_load_gvhmr_shapes_and_fps():
    p = load_gvhmr(FIXTURE)
    assert p.num_frames == 10
    assert p.global_orient.shape == (10, 3)
    assert p.body_pose.shape == (10, 21, 3)
    assert p.transl.shape == (10, 3)
    assert p.betas.shape == (10,)
    assert p.fps == GVHMR_FPS == 30.0
    for a in (p.global_orient, p.body_pose, p.transl, p.betas):
        assert isinstance(a, np.ndarray) and a.dtype == np.float32
        assert np.isfinite(a).all()


def test_load_gvhmr_rejects_other_dicts(tmp_path):
    import torch

    path = tmp_path / "bad.pt"
    torch.save({"smpl_params_incam": {}}, path)
    with pytest.raises(ValueError, match="smpl_params_global"):
        load_gvhmr(path)


@needs_body_model
def test_rest_skeleton_from_betas():
    s = rest_skeleton(load_gvhmr(FIXTURE).betas)
    assert s.joints.shape == (NUM_BODY_JOINTS, 3) == (22, 3)
    assert s.parents.tolist() == SMPLX_BODY_PARENTS
    assert len(s.names) == 22 and s.names[0] == "pelvis" and s.names[15] == "head"
    assert BODY_JOINT_NAMES.index("left_ankle") == 7
    # model frame is Y-up: head above pelvis above ankles, left side at +X
    head, pelvis, l_ankle, r_ankle = s.joints[[15, 0, 7, 8]]
    assert head[1] > pelvis[1] > l_ankle[1]
    assert l_ankle[0] > 0 > r_ankle[0]
    assert 1.2 < head[1] - l_ankle[1] < 1.9  # plausible adult, metres
    np.testing.assert_allclose(s.offsets()[1:] + s.joints[s.parents[1:]], s.joints[1:])


def test_rest_skeleton_missing_model(tmp_path):
    with pytest.raises(FileNotFoundError, match="SMPLX_NEUTRAL"):
        rest_skeleton(np.zeros(10, np.float32), body_models=tmp_path)


# A standing body in the SMPL-X model frame (Y-up, facing +Z, left at +X), metres
STANDING = {
    "pelvis": [0.0, 0.95, 0.0],
    "left_hip": [0.09, 0.88, 0.0],
    "right_hip": [-0.09, 0.88, 0.0],
    "head": [0.0, 1.62, 0.02],
    "left_ankle": [0.1, 0.08, -0.02],
    "right_ankle": [-0.1, 0.08, -0.02],
    "left_foot": [0.11, 0.02, 0.12],
    "right_foot": [-0.11, 0.02, 0.12],
}


def _pose(orient_aa, joints):
    """Rotate model-frame joints about the pelvis by a world orientation (root-only FK)."""
    r = axis_angle_to_matrix(np.asarray(orient_aa, dtype=np.float64))
    pelvis = np.asarray(joints["pelvis"])
    return {k: pelvis + r @ (np.asarray(v) - pelvis) for k, v in joints.items()}


def _check_upright_facing_plus_z(j):
    assert j["head"][1] > j["pelvis"][1] > j["left_ankle"][1] > j["left_foot"][1] >= 0
    assert j["left_hip"][0] > j["right_hip"][0]  # left at +X
    toes = (j["left_foot"] + j["right_foot"]) / 2 - (j["left_ankle"] + j["right_ankle"]) / 2
    assert toes[2] > 0.1 and abs(toes[0]) < 1e-6  # toes point at +Z
    # right-handed body: left x up = forward
    left = j["left_hip"] - j["right_hip"]
    up = j["head"] - j["pelvis"]
    assert np.cross(left, up)[2] > 0


def test_gvhmr_to_gltf_is_a_rotation_not_a_mirror():
    r = GVHMR_TO_GLTF.astype(np.float64)
    assert np.allclose(r @ r.T, np.eye(3))
    assert np.isclose(np.linalg.det(r), 1.0)
    assert np.allclose(r @ [0, 1, 0], [0, 1, 0])  # up stays up


def test_to_gltf_frame_standing_pose_facing_the_camera():
    # In GVHMR's world frame +Z looks away from the camera, so a performer facing the camera has
    # a 180-degree yaw. In glTF that performer must face the asset front (+Z) with no rotation.
    facing_camera = np.array([0.0, np.pi, 0.0])
    gv = _pose(facing_camera, STANDING)
    assert gv["left_hip"][0] < gv["right_hip"][0]  # GVHMR: the performer's left is at -X

    names = list(gv)
    pos, orient = to_gltf_frame(np.stack([gv[k] for k in names]), facing_camera)
    gl = dict(zip(names, pos, strict=True))
    _check_upright_facing_plus_z(gl)
    assert np.allclose(axis_angle_to_matrix(orient), np.eye(3), atol=1e-6)
    # converting the orientation and re-posing gives the same points as converting the points
    assert np.allclose(np.stack(list(_pose(orient, STANDING).values())), pos, atol=1e-6)


def test_to_gltf_frame_keeps_shape_and_dtype():
    pts = np.zeros((7, 22, 3), dtype=np.float32)
    rot = np.full((7, 3), 0.3, dtype=np.float32)
    p, r = to_gltf_frame(pts, rot)
    assert p.shape == pts.shape and p.dtype == np.float32
    assert r.shape == rot.shape and r.dtype == np.float32
    assert to_gltf_frame(pts)[1] is None


def test_axis_angle_round_trip():
    rng = np.random.default_rng(0)
    axes = rng.normal(size=(200, 3))
    axes /= np.linalg.norm(axes, axis=-1, keepdims=True)
    angles = np.concatenate([rng.uniform(0, np.pi, 196), [0.0, 1e-8, np.pi - 1e-5, np.pi]])
    aa = axes * angles[:, None]
    m = axis_angle_to_matrix(aa)
    assert np.allclose(m @ np.swapaxes(m, -1, -2), np.eye(3), atol=1e-9)
    assert np.allclose(axis_angle_to_matrix(matrix_to_axis_angle(m)), m, atol=1e-6)


@needs_body_model
def test_real_clip_in_gltf_frame():
    """walk-ur7zdb: on a treadmill, facing the camera. In glTF it stands up and faces +Z."""
    import smplx
    import torch

    p = load_gvhmr(FIXTURE)
    n = p.num_frames
    model = smplx.create(
        str(body_models_dir()),
        model_type="smplx",
        gender="neutral",
        num_betas=10,
        use_pca=False,
        flat_hand_mean=True,
        ext="npz",
        batch_size=n,
    )
    with torch.no_grad():
        out = model(
            betas=torch.as_tensor(p.betas).expand(n, -1),
            global_orient=torch.as_tensor(p.global_orient),
            body_pose=torch.as_tensor(p.body_pose.reshape(n, 63)),
            transl=torch.as_tensor(p.transl),
        )
    gv = out.joints[:, :NUM_BODY_JOINTS].numpy()
    j, _ = to_gltf_frame(gv, p.global_orient)
    pelvis, head = j[:, 0], j[:, 15]
    l_hip, r_hip = j[:, 1], j[:, 2]
    ankles, feet = j[:, [7, 8]], j[:, [10, 11]]

    assert (head[:, 1] - pelvis[:, 1] > 0.4).all()  # head above hips
    assert (feet[..., 1].min(axis=1) < pelvis[:, 1] - 0.7).all()  # feet near the floor
    assert (feet[..., 1].min(axis=1) < 0.25).all()  # GVHMR leaves a few cm; cleanup grounds it
    left = l_hip - r_hip
    forward = np.cross(left, head - pelvis)
    forward /= np.linalg.norm(forward, axis=-1, keepdims=True)
    assert (forward[:, 2] > 0.9).all()  # faces +Z, the glTF front, as it faces the camera
    toes = (feet - ankles).mean(axis=1)
    assert (toes[:, 2] > 0).all()
