import json
from pathlib import Path

import numpy as np
import pygltflib as gl
import pytest
from typer.testing import CliRunner

from anim8te.cli import app
from anim8te.library import ClipMeta, ClipStatus, read_meta, write_meta
from anim8te.skeleton import BONE_NAMES, PARENTS
from anim8te.stages.export import ExportError, Motion, build_gltf, run_export

FIXTURES = Path(__file__).parent / "fixtures"
FPS = 30.0
T = 12


def _motion_arrays(t: int = T) -> dict[str, np.ndarray]:
    """A small synthetic clean/motion.npz: random rest offsets, swinging rotations, moving hips."""
    rng = np.random.default_rng(0)
    offsets = rng.normal(scale=0.1, size=(22, 3)).astype(np.float32)
    offsets[0] = [0.0, -0.35, 0.0]  # Hips in the SMPL-X frame
    angle = np.linspace(0, 1, t)[:, None] * rng.uniform(0.1, 0.5, size=22)  # (t, 22) radians
    rot = np.zeros((t, 22, 4), dtype=np.float32)
    rot[..., 0] = np.sin(angle / 2)  # about +X
    rot[..., 3] = np.cos(angle / 2)
    hips = np.stack([np.zeros(t), np.full(t, 0.95), np.linspace(0, 0.4, t)], -1)
    return {
        "bone_names": np.array(BONE_NAMES),
        "parents": np.array(PARENTS, dtype=np.int64),
        "rest_offsets": offsets,
        "rotations": rot,
        "hips_translation": hips.astype(np.float32),
        "fps": np.float32(FPS),
        "betas": np.zeros(10, dtype=np.float32),
        "sole_y": np.float32(-1.3),
    }


def _read(gltf: gl.GLTF2, accessor: int) -> np.ndarray:
    acc = gltf.accessors[accessor]
    view = gltf.bufferViews[acc.bufferView]
    width = {gl.SCALAR: 1, gl.VEC3: 3, gl.VEC4: 4, gl.MAT4: 16}[acc.type]
    data = gltf.binary_blob()[view.byteOffset : view.byteOffset + view.byteLength]
    return np.frombuffer(data, dtype=np.float32).reshape(acc.count, width)


def _cleaned_clip(library: Path, arrays: dict[str, np.ndarray] | None = None) -> Path:
    meta = ClipMeta.model_validate_json((FIXTURES / "meta.json").read_text()).model_copy(
        update={"id": "walk-test01", "status": ClipStatus.cleaned}
    )
    clip = library / "clips" / meta.id
    (clip / "clean").mkdir(parents=True)
    np.savez(clip / "clean" / "motion.npz", **(arrays or _motion_arrays()))
    write_meta(clip, meta)
    return clip


def test_skeleton_nodes_and_skin(tmp_path):
    np.savez(tmp_path / "m.npz", **_motion_arrays())
    motion = Motion.load(tmp_path / "m.npz")
    gltf = build_gltf(motion, "walk")

    assert gltf.nodes[0].name == "Armature" and gltf.nodes[0].children == [1]
    assert [n.name for n in gltf.nodes[1:]] == list(BONE_NAMES)
    for i, p in enumerate(PARENTS):
        if p >= 0:
            assert i + 1 in gltf.nodes[p + 1].children
        assert gltf.nodes[i + 1].rotation is None  # identity rest rotation

    rest = np.array([n.translation for n in gltf.nodes[1:]])
    np.testing.assert_allclose(rest[1:], motion.rest_offsets[1:], atol=1e-6)
    np.testing.assert_allclose(rest[0], [0.0, -0.35 + 1.3, 0.0], atol=1e-6)  # soles at y = 0

    (skin,) = gltf.skins
    assert skin.joints == list(range(1, 23)) and skin.skeleton == 1
    ibm = _read(gltf, skin.inverseBindMatrices).reshape(22, 4, 4).transpose(0, 2, 1)
    world = rest.copy()
    for i, p in enumerate(PARENTS):
        if p >= 0:
            world[i] += world[p]
    np.testing.assert_allclose(ibm[:, :3, 3], -world, atol=1e-5)
    np.testing.assert_allclose(ibm[:, :3, :3], np.tile(np.eye(3), (22, 1, 1)))


def test_animation_channels_and_timing(tmp_path):
    arrays = _motion_arrays()
    np.savez(tmp_path / "m.npz", **arrays)
    gltf = build_gltf(Motion.load(tmp_path / "m.npz"), "walk-test01")

    (anim,) = gltf.animations
    assert anim.name == "walk-test01"
    targets = [(c.target.node, c.target.path) for c in anim.channels]
    assert targets[0] == (1, "translation")
    assert sorted(n for n, p in targets if p == "rotation") == list(range(1, 23))
    assert len(targets) == 23

    times_acc = gltf.accessors[anim.samplers[0].input]
    times = _read(gltf, anim.samplers[0].input)[:, 0]
    np.testing.assert_allclose(times, np.arange(T) / FPS, atol=1e-6)
    assert times_acc.min == [0.0] and times_acc.max[0] == pytest.approx((T - 1) / FPS)

    for c in anim.channels:
        s = anim.samplers[c.sampler]
        assert s.interpolation == "LINEAR" and s.input == anim.samplers[0].input
        values = _read(gltf, s.output)
        if c.target.path == "translation":
            np.testing.assert_allclose(values, arrays["hips_translation"], atol=1e-6)
        else:
            np.testing.assert_allclose(values, arrays["rotations"][:, c.target.node - 1], atol=1e-6)


def test_export_writes_glb_and_sets_status(tmp_path):
    clip = _cleaned_clip(tmp_path)
    result = run_export(tmp_path, "walk-test01")
    assert result.glb == clip / "motion.glb" and result.glb.read_bytes()[:4] == b"glTF"
    assert result.num_frames == T and result.duration_s == pytest.approx((T - 1) / FPS)
    assert read_meta(clip).status == ClipStatus.exported

    gltf = gl.GLTF2().load(str(result.glb))
    assert gltf.animations[0].name == "walk-test01"
    assert len(gltf.nodes) == 23 and gltf.meshes == []

    first = result.glb.read_bytes()
    run_export(tmp_path, "walk-test01")  # deterministic re-run
    assert result.glb.read_bytes() == first


def test_export_refuses_uncleaned_and_old_motion(tmp_path):
    clip = _cleaned_clip(tmp_path)
    write_meta(clip, read_meta(clip).model_copy(update={"status": ClipStatus.extracted}))
    with pytest.raises(ExportError, match="not cleaned"):
        run_export(tmp_path, "walk-test01")

    old = _motion_arrays()
    del old["sole_y"]
    _cleaned_clip(tmp_path / "old", old)
    with pytest.raises(ExportError, match="re-run `anim8te clean`"):
        run_export(tmp_path / "old", "walk-test01")


def test_export_cli(tmp_path):
    clip = _cleaned_clip(tmp_path)
    res = CliRunner().invoke(app, ["--library", str(tmp_path), "export", "walk-test01"])
    assert res.exit_code == 0, res.output
    assert "animation: walk-test01" in res.output and "status:    exported" in res.output
    assert json.loads((clip / "meta.json").read_text())["status"] == "exported"

    res = CliRunner().invoke(app, ["--library", str(tmp_path), "export", "nope-000000"])
    assert res.exit_code == 1 and "no clip" in res.output
