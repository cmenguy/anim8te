from pathlib import Path

import numpy as np
import pytest

from anim8te.convert import (
    BODY_JOINT_NAMES,
    GVHMR_FPS,
    NUM_BODY_JOINTS,
    body_models_dir,
    load_gvhmr,
    rest_skeleton,
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
