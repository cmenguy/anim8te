from pathlib import Path

import numpy as np
import pytest

from anim8te.convert import BODY_JOINT_NAMES, body_models_dir, load_gvhmr
from anim8te.skeleton import (
    BONE_NAMES,
    PARENTS,
    ROOT,
    SMPLX_TO_HUMANOID,
    canonical_skeleton,
    performer_betas,
    performer_betas_path,
    read_performer_betas,
)

FIXTURE = Path(__file__).parent / "fixtures" / "hmr4d_walk_10f.pt"

needs_body_model = pytest.mark.skipif(
    not (body_models_dir() / "smplx" / "SMPLX_NEUTRAL.npz").is_file(),
    reason="SMPL-X body model not installed (docs/checkpoints.md)",
)

# The SkeletonProfileHumanoid bones without fingers (Godot 4 skeleton_profile.cpp)
HUMANOID_BODY = {
    "Hips", "Spine", "Chest", "UpperChest", "Neck", "Head",
    *(f"{side}{bone}" for side in ("Left", "Right") for bone in (
        "Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toes",
    )),
}  # fmt: skip


def test_every_smplx_joint_maps_to_exactly_one_humanoid_name():
    assert set(SMPLX_TO_HUMANOID) == set(BODY_JOINT_NAMES)
    assert len(BODY_JOINT_NAMES) == 22
    assert len(set(SMPLX_TO_HUMANOID.values())) == 22  # no two joints share a name
    assert set(SMPLX_TO_HUMANOID.values()) == HUMANOID_BODY
    assert BONE_NAMES == tuple(SMPLX_TO_HUMANOID[j] for j in BODY_JOINT_NAMES)


def test_parents_form_a_single_tree_rooted_at_hips():
    n = len(BONE_NAMES)
    assert len(PARENTS) == n
    roots = [i for i, p in enumerate(PARENTS) if p == -1]
    assert roots == [BONE_NAMES.index(ROOT)] == [0]
    for i, p in enumerate(PARENTS):
        if p != -1:
            assert 0 <= p < i  # parents come first: no cycles, a valid glTF node order
    # every bone reaches Hips
    for i in range(n):
        seen, j = set(), i
        while j != -1:
            assert j not in seen
            seen.add(j)
            j = PARENTS[j]
        assert 0 in seen


def test_hierarchy_is_anatomical():
    parent = {BONE_NAMES[i]: BONE_NAMES[p] for i, p in enumerate(PARENTS) if p != -1}
    for side in ("Left", "Right"):
        assert parent[f"{side}UpperLeg"] == "Hips"
        assert parent[f"{side}LowerLeg"] == f"{side}UpperLeg"
        assert parent[f"{side}Foot"] == f"{side}LowerLeg"
        assert parent[f"{side}Toes"] == f"{side}Foot"
        assert parent[f"{side}Shoulder"] == "UpperChest"
        assert parent[f"{side}UpperArm"] == f"{side}Shoulder"
        assert parent[f"{side}LowerArm"] == f"{side}UpperArm"
        assert parent[f"{side}Hand"] == f"{side}LowerArm"
    assert parent["Spine"] == "Hips"
    assert parent["Chest"] == "Spine"
    assert parent["UpperChest"] == "Chest"
    assert parent["Neck"] == "UpperChest"
    assert parent["Head"] == "Neck"


@needs_body_model
def test_canonical_skeleton_rest_pose_from_betas():
    betas = load_gvhmr(FIXTURE).betas
    s = canonical_skeleton(betas)
    assert s.names == BONE_NAMES and s.parents == PARENTS
    assert s.rest_positions.shape == (22, 3)
    np.testing.assert_array_equal(s.betas, betas)
    pos = {name: s.rest_positions[s.index(name)] for name in s.names}
    assert pos["Head"][1] > pos["Hips"][1] > pos["LeftFoot"][1]
    assert pos["LeftUpperArm"][0] > 0 > pos["RightUpperArm"][0]  # left at +X
    assert pos["LeftToes"][2] > pos["LeftFoot"][2]  # toes point forward, +Z
    offsets = s.rest_offsets()
    np.testing.assert_allclose(offsets[0], s.rest_positions[0])
    np.testing.assert_allclose(
        offsets[1:] + s.rest_positions[list(s.parents[1:])], s.rest_positions[1:], atol=1e-6
    )
    assert sorted(s.children(s.index("UpperChest"))) == [
        s.index("Neck"), s.index("LeftShoulder"), s.index("RightShoulder")
    ]  # fmt: skip


@needs_body_model
def test_body_shape_changes_rest_pose():
    a = canonical_skeleton(np.zeros(10, np.float32))
    tall = np.zeros(10, np.float32)
    tall[0] = 2.0
    b = canonical_skeleton(tall)
    assert not np.allclose(a.rest_positions, b.rest_positions)


def test_performer_betas_stored_once_and_reused(tmp_path):
    first = np.arange(10, dtype=np.float32) / 10
    second = -first
    assert read_performer_betas(tmp_path, "perf01") is None
    got = performer_betas(tmp_path, "perf01", first, source_clip="walk-aaaaaa")
    np.testing.assert_array_equal(got, first)
    assert performer_betas_path(tmp_path, "perf01").is_file()
    # a later clip of the same performer gets the first clip's shape, not its own
    got = performer_betas(tmp_path, "perf01", second, source_clip="jog-bbbbbb")
    np.testing.assert_array_equal(got, first)
    np.testing.assert_array_equal(read_performer_betas(tmp_path, "perf01"), first)
    # another performer has its own shape
    np.testing.assert_array_equal(performer_betas(tmp_path, "perf02", second, "x-cccccc"), second)


def test_read_performer_betas_rejects_wrong_length(tmp_path):
    path = performer_betas_path(tmp_path, "perf01")
    path.parent.mkdir(parents=True)
    path.write_text('{"betas": [0.0, 1.0]}')
    with pytest.raises(ValueError, match="10 betas"):
        read_performer_betas(tmp_path, "perf01")
