import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from anim8te.cli import app
from anim8te.convert import body_models_dir
from anim8te.library import ClipMeta, ClipStatus, Filter, read_features, write_meta
from anim8te.skeleton import BONE_NAMES
from anim8te.stages.clean import CleanError, resolve_filters
from anim8te.stages.features import (
    CONTACT_BONES,
    DEFAULT_CONTACTS,
    compute_features,
    derivative,
    detect_contacts,
    drop_short_runs,
    estimate_ground_velocity,
)

FIXTURES = Path(__file__).parent / "fixtures"
FPS = 30.0

needs_body_model = pytest.mark.skipif(
    not (body_models_dir() / "smplx" / "SMPLX_NEUTRAL.npz").is_file(),
    reason="SMPL-X body model not installed (docs/checkpoints.md)",
)


def _walk(speed: float, treadmill: bool, seconds: float = 4.0, seed: int = 0):
    """Synthetic walk: two feet half a cycle apart, 1 s cycle, 60 % stance.

    Returns sole heights (T, 2), velocities (T, 2, 3) and the true stance mask (T, 2). The
    stance foot stands still overground; on a treadmill the whole body stays in place, so every
    foot velocity is the overground one minus the walking speed (the belt).
    """
    t = np.arange(int(seconds * FPS)) / FPS
    rng = np.random.default_rng(seed)
    heights, vz, stance = [], [], []
    for offset in (0.0, 0.5):
        phase = (t + offset) % 1.0
        swing = phase >= 0.6
        u = np.clip((phase - 0.6) / 0.4, 0, 1)  # 0..1 through the swing
        heights.append(np.where(swing, 0.12 * np.sin(np.pi * u), 0.0))
        # the swing covers one stride (speed * 1 s) in 0.4 s, sin^2 velocity profile
        vz.append(np.where(swing, 2 * speed / 0.4 * np.sin(np.pi * u) ** 2, 0.0))
        stance.append(~swing)
    heights = np.stack(heights, -1) + rng.normal(scale=0.003, size=(len(t), 2))
    vel = np.zeros((len(t), 2, 3))
    vel[..., 2] = np.stack(vz, -1) - (speed if treadmill else 0.0)
    vel[..., [0, 2]] += rng.normal(scale=0.05, size=(len(t), 2, 2))
    return heights, vel, np.stack(stance, -1)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(int), [0]])))
    return list(zip(edges[::2], edges[1::2], strict=True))


@pytest.mark.parametrize("treadmill", [True, False])
def test_synthetic_walk_gets_alternating_contacts(treadmill):
    heights, vel, stance = _walk(speed=1.2, treadmill=treadmill)
    contacts, ground = detect_contacts(heights, vel, DEFAULT_CONTACTS)

    # the ground is the belt on a treadmill, still otherwise
    np.testing.assert_allclose(ground, [0.0, -1.2 if treadmill else 0.0], atol=0.05)
    # contacts match the stance phases
    assert (contacts == stance).mean() > 0.9
    assert not (contacts & (heights > 0.06)).any()  # never while the foot is up
    # one contact per step, and left and right steps alternate
    left, right = _runs(contacts[:, 0]), _runs(contacts[:, 1])
    assert len(left) >= 4 and len(right) >= 4
    # (both feet may already be down at frame 0, so heel strikes are the runs starting later)
    starts = sorted([(s, "L") for s, _ in left if s] + [(s, "R") for s, _ in right if s])
    sides = [side for _, side in starts]
    assert all(a != b for a, b in zip(sides, sides[1:], strict=False)), sides


def test_treadmill_contacts_need_the_belt_velocity():
    heights, vel, _ = _walk(speed=1.2, treadmill=True)
    still_ground = {**DEFAULT_CONTACTS, "ground_velocity": [0.0, 0.0]}
    assert not detect_contacts(heights, vel, still_ground)[0].any()  # stance slides at 1.2 m/s
    belt = {**DEFAULT_CONTACTS, "ground_velocity": [0.0, -1.2]}
    contacts, ground = detect_contacts(heights, vel, belt)
    assert contacts.any() and ground.tolist() == [0.0, -1.2]


def test_ground_velocity_follows_the_lowest_joint():
    heights = np.array([[0.0, 0.1], [0.1, 0.0], [0.0, 0.1]])
    vel = np.zeros((3, 2, 3))
    vel[:, :, 2] = [[-1, 5], [5, -1], [-1, 5]]
    np.testing.assert_allclose(estimate_ground_velocity(heights, vel), [0, -1])


def test_short_contact_runs_are_dropped():
    mask = np.array([[1, 1, 0, 1, 1, 1, 0, 1]], dtype=bool).T
    out = drop_short_runs(mask, 3)
    assert out[:, 0].astype(int).tolist() == [0, 0, 0, 1, 1, 1, 0, 0]


def test_derivatives_of_a_cubic():
    t = np.arange(30) / FPS
    x = 2 * t**3
    np.testing.assert_allclose(derivative(x, FPS)[3:-3], 6 * t[3:-3] ** 2, atol=1e-2)
    np.testing.assert_allclose(derivative(x, FPS, order=3)[4:-4], 12.0, atol=1e-6)


def test_compute_features_shapes_and_root_track():
    heights, vel, _ = _walk(speed=1.2, treadmill=False, seconds=2.0)
    t = len(heights)
    pos = np.zeros((t, 22, 3))
    pos[:, 0] = np.stack([np.zeros(t), np.full(t, 0.9), 1.2 * np.arange(t) / FPS], -1)
    rest_above_sole = np.array([0.08, 0.08, 0.02, 0.02])
    idx = [BONE_NAMES.index(b) for b in CONTACT_BONES]
    for k, i in enumerate(idx):
        foot = k % 2  # LeftFoot, RightFoot, LeftToes, RightToes
        pos[:, i, 1] = heights[:, foot] + rest_above_sole[k]
        pos[:, i, 2] = np.cumsum(vel[:, foot, 2]) / FPS
    f = compute_features(pos, list(BONE_NAMES), rest_above_sole, FPS, DEFAULT_CONTACTS)

    assert f.num_frames == t and len(f.joint_positions) == t and len(f.joint_positions[0]) == 22
    assert set(f.contacts) == set(CONTACT_BONES) and len(f.contacts["LeftToes"]) == t
    assert f.contact_thresholds.speed_mps == DEFAULT_CONTACTS["speed_mps"]
    np.testing.assert_allclose(np.array(f.root_velocity)[:, 2], 1.2, atol=1e-6)
    assert np.array(f.joint_jerk).shape == (t, 22)
    assert np.allclose(np.array(f.joint_jerk)[:, 0], 0)  # constant velocity: no jerk
    assert f.rest_heights_above_sole == dict(zip(CONTACT_BONES, rest_above_sole, strict=True))

    off = compute_features(pos, list(BONE_NAMES), rest_above_sole, FPS, None)
    assert off.contacts == {} and off.contact_thresholds is None
    assert off.rest_heights_above_sole == f.rest_heights_above_sole  # penetration needs it too


def _meta(**kw) -> ClipMeta:
    return ClipMeta.model_validate_json((FIXTURES / "meta.json").read_text()).model_copy(update=kw)


def test_resolve_filters_validates_contacts():
    filters = resolve_filters(_meta(filters={"contacts": Filter(params={"height_m": 0.05})}))
    assert filters["contacts"].params == {**DEFAULT_CONTACTS, "height_m": 0.05}
    for bad, msg in [
        ({"height_m": 0}, "height_m"),
        ({"min_frames": 0}, "min_frames"),
        ({"ground_velocity": "belt"}, "ground_velocity"),
        ({"ground_velocity": [1.0]}, "ground_velocity"),
    ]:
        with pytest.raises(CleanError, match=msg):
            resolve_filters(_meta(filters={"contacts": Filter(params=bad)}))


def _extracted_clip(library: Path) -> Path:
    meta = _meta(id="walk-test01", selected_take=1, status=ClipStatus.extracted)
    clip = library / "clips" / meta.id
    (clip / "gvhmr").mkdir(parents=True)
    shutil.copy(FIXTURES / "hmr4d_walk_10f.pt", clip / "gvhmr" / "hmr4d_results.pt")
    write_meta(clip, meta)
    return clip


@needs_body_model
def test_clean_writes_features(tmp_path):
    clip = _extracted_clip(tmp_path)
    args = ["--library", str(tmp_path), "clean", "walk-test01"]
    res = CliRunner().invoke(app, args)
    assert res.exit_code == 0, res.output
    assert "features:" in res.output and "frames in contact" in res.output
    f = read_features(clip)
    assert f.num_frames == 10 and f.fps == 30.0 and f.bone_names[0] == "Hips"
    assert set(f.contacts) == set(CONTACT_BONES)
    motion = np.load(clip / "clean" / "motion.npz")
    np.testing.assert_allclose(f.root_position, motion["hips_translation"], atol=1e-4)
    meta = json.loads((clip / "meta.json").read_text())
    assert meta["filters"]["contacts"]["params"] == DEFAULT_CONTACTS

    res = CliRunner().invoke(app, [*args, "--no-contacts"])
    assert res.exit_code == 0, res.output
    assert read_features(clip).contacts == {}
