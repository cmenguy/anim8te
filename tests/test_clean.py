import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from anim8te.cli import app
from anim8te.convert import axis_angle_to_matrix, body_models_dir
from anim8te.library import ClipMeta, ClipStatus, Filter, read_meta, write_meta
from anim8te.skeleton import PARENTS
from anim8te.stages.clean import (
    DEFAULT_FILTERS,
    CleanError,
    forward_kinematics,
    ground_offset,
    matrix_to_quaternion,
    quaternion_to_matrix,
    resolve_filters,
    run_clean,
    savgol,
    smooth_quaternions,
)

FIXTURES = Path(__file__).parent / "fixtures"

needs_body_model = pytest.mark.skipif(
    not (body_models_dir() / "smplx" / "SMPLX_NEUTRAL.npz").is_file(),
    reason="SMPL-X body model not installed (docs/checkpoints.md)",
)


def _roughness(x: np.ndarray) -> float:
    """Mean squared second difference along time: what jitter adds and smoothing removes."""
    return float((np.diff(x, n=2, axis=0) ** 2).mean())


def test_savgol_keeps_polynomials_up_to_its_order():
    t = np.arange(40, dtype=np.float64)
    cubic = 0.001 * t**3 - 0.05 * t**2 + t - 3
    np.testing.assert_allclose(savgol(cubic, 9, 3), cubic, atol=1e-8)  # edges included


def test_savgol_window_longer_than_clip_shrinks():
    x = np.random.default_rng(0).normal(size=(6, 2))
    assert savgol(x, 9, 3).shape == (6, 2)  # 5-frame window
    np.testing.assert_array_equal(savgol(x[:3], 9, 3), x[:3])  # too short for order 3


def test_jittered_signal_gets_smoother():
    rng = np.random.default_rng(1)
    t = np.arange(150) / 30.0
    clean = np.stack([np.sin(2 * np.pi * t), 0.9 + 0.05 * np.cos(4 * np.pi * t)], -1)
    noisy = clean + rng.normal(scale=0.01, size=clean.shape)
    out = savgol(noisy, 9, 3)
    assert _roughness(out - clean) < 0.1 * _roughness(noisy - clean)  # jitter left
    assert _roughness(out) < _roughness(noisy)
    assert np.abs(out - clean).mean() < 0.6 * np.abs(noisy - clean).mean()


def test_quaternion_round_trip_and_gltf_order():
    rng = np.random.default_rng(2)
    aa = rng.normal(size=(200, 3))
    aa[:4] = [[0, 0, 0], [np.pi, 0, 0], [0, np.pi, 0], [0, 0, np.pi]]  # all four branches
    m = axis_angle_to_matrix(aa)
    q = matrix_to_quaternion(m)
    np.testing.assert_allclose(np.linalg.norm(q, axis=-1), 1.0, atol=1e-12)
    np.testing.assert_allclose(quaternion_to_matrix(q), m, atol=1e-9)
    # 90 degrees about +Y is (0, sin 45, 0, cos 45) in glTF's (x, y, z, w)
    q90 = matrix_to_quaternion(axis_angle_to_matrix(np.array([0, np.pi / 2, 0])))
    np.testing.assert_allclose(np.abs(q90), [0, np.sqrt(0.5), 0, np.sqrt(0.5)], atol=1e-12)


def test_jittered_rotations_get_smoother_across_sign_flips():
    rng = np.random.default_rng(3)
    t = np.arange(120) / 30.0
    angle = 0.6 * np.sin(2 * np.pi * t)
    clean = matrix_to_quaternion(axis_angle_to_matrix(angle[:, None] * [0.0, 0.0, 1.0]))
    noisy_aa = angle[:, None] * [0.0, 0.0, 1.0] + rng.normal(scale=0.03, size=(120, 3))
    noisy = matrix_to_quaternion(axis_angle_to_matrix(noisy_aa))
    noisy[::7] *= -1  # same rotations, opposite hemisphere: must not be averaged into garbage
    out = smooth_quaternions(noisy, 9, 3)
    np.testing.assert_allclose(np.linalg.norm(out, axis=-1), 1.0, atol=1e-12)

    def err(q):  # angle to the clean rotation, sign-independent
        return 2 * np.arccos(np.clip(np.abs((q * clean).sum(-1)), 0, 1))

    assert err(out).mean() < 0.6 * err(noisy).mean()
    rel = quaternion_to_matrix(out[1:]) @ np.swapaxes(quaternion_to_matrix(out[:-1]), -1, -2)
    step = np.arccos(np.clip((np.trace(rel, axis1=-2, axis2=-1) - 1) / 2, -1, 1))
    assert step.max() < 0.2  # no frame-to-frame jumps left


def test_forward_kinematics_rest_pose_and_rotation():
    offsets = np.array([[0, 1, 0], [0, -0.5, 0], [0, -0.5, 0.0]] + [[0, 0, 0]] * 19)
    rot = np.broadcast_to(np.eye(3), (2, 22, 3, 3)).copy()
    hips = np.array([[0, 1, 0], [1, 1, 0.0]])
    pos = forward_kinematics(rot, hips, offsets, PARENTS)
    np.testing.assert_allclose(pos[0, 1], [0, 0.5, 0])
    rot[1, 0] = axis_angle_to_matrix(np.array([0, 0, np.pi / 2]))  # hips turned 90 about Z
    pos = forward_kinematics(rot, hips, offsets, PARENTS)
    np.testing.assert_allclose(pos[1, 1], [1.5, 1, 0], atol=1e-12)


def test_ground_alignment_puts_lowest_foot_at_zero():
    rng = np.random.default_rng(4)
    t = np.arange(150)
    # two feet alternating contact around y = -0.37 (a clip floating below the floor)
    left = -0.37 + 0.1 * np.clip(np.sin(t / 5.0), 0, None)
    right = -0.37 + 0.1 * np.clip(-np.sin(t / 5.0), 0, None)
    soles = np.stack([left, right], -1) + rng.normal(scale=0.002, size=(150, 2))
    soles[40, 0] = -0.6  # one bad frame dips 23 cm: the percentile ignores it
    offset = ground_offset(soles, 5.0)
    grounded = soles - offset
    lowest = grounded.min(axis=1)
    assert abs(np.percentile(lowest, 5)) < 1e-9
    assert abs(np.median(lowest)) < 0.01  # contacts sit about at y = 0
    assert lowest.min() < -0.2  # the outlier stays an outlier, it did not move the clip


def _meta(**kw) -> ClipMeta:
    return ClipMeta.model_validate_json((FIXTURES / "meta.json").read_text()).model_copy(update=kw)


def test_resolve_filters_fills_defaults_and_validates():
    filters = resolve_filters(_meta(filters={"smooth": Filter(params={"window": 11})}))
    assert filters["smooth"].params == {**DEFAULT_FILTERS["smooth"], "window": 11}
    assert filters["ground"].params == DEFAULT_FILTERS["ground"]
    with pytest.raises(CleanError, match="odd"):
        resolve_filters(_meta(filters={"smooth": Filter(params={"window": 8})}))
    with pytest.raises(CleanError, match="unknown parameter"):
        resolve_filters(_meta(filters={"ground": Filter(params={"pct": 5})}))
    with pytest.raises(CleanError, match="savgol"):
        resolve_filters(_meta(filters={"smooth": Filter(params={"method": "one_euro"})}))


def _extracted_clip(library: Path) -> Path:
    meta = _meta(id="walk-test01", selected_take=1, status=ClipStatus.extracted)
    clip = library / "clips" / meta.id
    (clip / "gvhmr").mkdir(parents=True)
    shutil.copy(FIXTURES / "hmr4d_walk_10f.pt", clip / "gvhmr" / "hmr4d_results.pt")
    write_meta(clip, meta)
    return clip


def test_clean_refuses_a_clip_that_is_not_extracted(tmp_path):
    clip = _extracted_clip(tmp_path)
    write_meta(clip, read_meta(clip).model_copy(update={"status": ClipStatus.generated}))
    with pytest.raises(CleanError, match="not extracted"):
        run_clean(tmp_path, "walk-test01")


@needs_body_model
def test_clean_writes_motion_and_filters_and_is_idempotent(tmp_path):
    clip = _extracted_clip(tmp_path)
    result = run_clean(tmp_path, "walk-test01", overrides={"smooth": {"window": 7}})
    meta = read_meta(clip)
    assert meta.status == ClipStatus.cleaned
    assert meta.filters["smooth"].params["window"] == 7  # written back with the defaults
    assert meta.filters["ground"].params == DEFAULT_FILTERS["ground"]

    first = dict(np.load(result.motion))
    assert first["rotations"].shape == (10, 22, 4)
    assert first["hips_translation"].shape == (10, 3)
    assert first["bone_names"][0] == "Hips" and float(first["fps"]) == 30.0
    np.testing.assert_allclose(np.linalg.norm(first["rotations"], axis=-1), 1.0, atol=1e-5)
    assert 0.7 < first["hips_translation"][:, 1].mean() < 1.1  # standing hips, feet on the floor
    # rest Hips above the soles is a standing height too (export puts the rest pose on the floor)
    assert 0.7 < first["rest_offsets"][0, 1] - first["sole_y"] < 1.1

    # second run reads the filters back from meta.json and starts from the raw GVHMR output
    run_clean(tmp_path, "walk-test01")
    second = dict(np.load(result.motion))
    for k in first:
        np.testing.assert_array_equal(first[k], second[k])
    assert read_meta(clip).filters == meta.filters
    assert (tmp_path / "performers" / "perf01" / "betas.json").is_file()


@needs_body_model
def test_clean_cli_toggles_and_params(tmp_path):
    clip = _extracted_clip(tmp_path)
    args = ["--library", str(tmp_path), "clean", "walk-test01"]
    res = CliRunner().invoke(app, [*args, "--no-ground", "--set", "smooth.order=2"])
    assert res.exit_code == 0, res.output
    meta = json.loads((clip / "meta.json").read_text())
    assert meta["filters"]["ground"]["enabled"] is False
    assert meta["filters"]["smooth"]["params"]["order"] == 2
    assert "ground:    off" in res.output

    res = CliRunner().invoke(app, [*args, "--set", "smooth.window=8"])
    assert res.exit_code == 1 and "odd integer" in res.output
