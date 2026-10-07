"""Stage 5.7: write `motion.glb` on the canonical skeleton (GDD §4 stage 5).

`run_export` reads `clean/motion.npz` and writes the clip's `motion.glb`: a skeleton-only glTF
(no mesh) with

- one node per canonical bone, parented as in the SMPL-X tree, under a scene root node named
  `Armature`. Rest rotations are the identity; rest translations are the offsets from M1.8, with
  Hips moved so the rest pose stands with its soles at y = 0, and the spine and neck offsets
  (`STRAIGHT_BONES`) turned vertical with their lengths kept.
- one skin over those 22 joints, so importers (Godot included) build a skeleton from it. The
  inverse bind matrices are the inverse rest world transforms, pure translations here.
- one animation named after the clip id: a rotation channel for every bone and a translation
  channel for Hips, LINEAR, one key per frame at `frame / fps` seconds.

Everything is in the glTF frame already (Y-up, right-handed, metres, facing +Z), so values are
written as they come out of `anim8te clean`.

Why the straight spine (M2.12): SMPL-X's rest spine is kinked (UpperChest sits behind Chest, the
neck leans back). Godot's humanoid retarget ("overwrite axis") transfers bone directions, not
rotations from rest, so the kink reached the mannequin as a hunch with the head pushed forward.
With vertical rest offsets the rest spine points straight up like a game rig's, and the
unchanged local rotations bend it as GVHMR measured. Arms and legs keep their SMPL-X offsets.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pygltflib as gl
from pydantic import BaseModel

from anim8te.library import ClipMeta, ClipStatus, clip_dir, read_meta, write_meta
from anim8te.stages.clean import CLEAN_DIR, MOTION_FILE

GLB_FILE = "motion.glb"
ROOT_NODE = "Armature"
GENERATOR = "anim8te export"

# bones whose rest offset from their parent is made vertical (same length), see the docstring
STRAIGHT_BONES = ("Spine", "Chest", "UpperChest", "Neck", "Head")

_READY = {ClipStatus.cleaned, ClipStatus.exported, ClipStatus.ready}


class ExportError(Exception):
    """Anything that stops an export; the message is meant for the user as is."""


class ExportResult(BaseModel):
    clip: Path
    meta: ClipMeta
    glb: Path
    animation: str
    num_frames: int
    fps: float
    duration_s: float
    size_bytes: int


@dataclass(frozen=True)
class Motion:
    """The contents of `clean/motion.npz`."""

    bone_names: tuple[str, ...]
    parents: tuple[int, ...]
    rest_offsets: np.ndarray  # (J, 3); row 0 is the Hips rest position in the SMPL-X frame
    rotations: np.ndarray  # (T, J, 4) local rotations, (x, y, z, w)
    hips_translation: np.ndarray  # (T, 3)
    fps: float
    sole_y: float  # rest-pose sole height in the SMPL-X frame

    @property
    def num_frames(self) -> int:
        return self.rotations.shape[0]

    @classmethod
    def load(cls, path: Path) -> Motion:
        with np.load(path) as d:
            if "sole_y" not in d:
                raise ExportError(f"{path} predates M1.10; re-run `anim8te clean`")
            return cls(
                bone_names=tuple(str(n) for n in d["bone_names"]),
                parents=tuple(int(p) for p in d["parents"]),
                rest_offsets=d["rest_offsets"].astype(np.float32),
                rotations=d["rotations"].astype(np.float32),
                hips_translation=d["hips_translation"].astype(np.float32),
                fps=float(d["fps"]),
                sole_y=float(d["sole_y"]),
            )

    def rest_translations(self) -> np.ndarray:
        """(J, 3) node rest translations: parent offsets, Hips lifted so the soles sit at y = 0,
        the `STRAIGHT_BONES` offsets turned to +Y with their lengths kept."""
        out = self.rest_offsets.astype(np.float32).copy()
        out[0, 1] -= self.sole_y
        for name in STRAIGHT_BONES:
            i = self.bone_names.index(name)
            out[i] = (0.0, np.linalg.norm(out[i]), 0.0)
        return out


class _Bin:
    """Accumulates the GLB binary chunk and the accessors that view it."""

    def __init__(self, gltf: gl.GLTF2) -> None:
        self.gltf = gltf
        self.data = bytearray()

    def add(self, array: np.ndarray, type_: str, *, minmax: bool = False) -> int:
        array = np.ascontiguousarray(array, dtype=np.float32)
        while len(self.data) % 4:
            self.data.append(0)
        offset = len(self.data)
        self.data += array.tobytes()
        self.gltf.bufferViews.append(
            gl.BufferView(buffer=0, byteOffset=offset, byteLength=array.nbytes)
        )
        width = {gl.SCALAR: 1, gl.VEC3: 3, gl.VEC4: 4, gl.MAT4: 16}[type_]
        flat = array.reshape(-1, width)
        acc = gl.Accessor(
            bufferView=len(self.gltf.bufferViews) - 1,
            componentType=gl.FLOAT,
            count=flat.shape[0],
            type=type_,
        )
        if minmax:
            acc.min = flat.min(axis=0).tolist()
            acc.max = flat.max(axis=0).tolist()
        self.gltf.accessors.append(acc)
        return len(self.gltf.accessors) - 1


def build_gltf(motion: Motion, animation_name: str) -> gl.GLTF2:
    """The skeleton, its skin and one animation as a glTF document with its binary blob set."""
    j = len(motion.bone_names)
    if any(p >= i for i, p in enumerate(motion.parents)):
        raise ValueError("parents must come before children")
    if motion.rotations.shape[1:] != (j, 4) or motion.hips_translation.shape[1:] != (3,):
        raise ValueError("motion arrays do not match the skeleton")

    gltf = gl.GLTF2(asset=gl.Asset(version="2.0", generator=GENERATOR))
    buf = _Bin(gltf)
    rest = motion.rest_translations()

    # node 0 is the scene root; bone i is node i + 1
    gltf.nodes.append(gl.Node(name=ROOT_NODE, children=[1]))
    for i, name in enumerate(motion.bone_names):
        children = [c + 1 for c, p in enumerate(motion.parents) if p == i]
        gltf.nodes.append(gl.Node(name=name, translation=rest[i].tolist(), children=children))
    joints = list(range(1, j + 1))

    # rest world transforms are translations only (identity rest rotations)
    world = rest.astype(np.float64).copy()
    for i, p in enumerate(motion.parents):
        if p >= 0:
            world[i] += world[p]
    ibm = np.tile(np.eye(4), (j, 1, 1))
    ibm[:, :3, 3] = -world
    ibm_acc = buf.add(ibm.transpose(0, 2, 1), gl.MAT4)  # glTF matrices are column-major
    gltf.skins.append(
        gl.Skin(name=ROOT_NODE, joints=joints, skeleton=1, inverseBindMatrices=ibm_acc)
    )

    times = buf.add(np.arange(motion.num_frames) / motion.fps, gl.SCALAR, minmax=True)
    anim = gl.Animation(name=animation_name)

    def channel(node: int, path: str, values: np.ndarray, type_: str) -> None:
        anim.samplers.append(
            gl.AnimationSampler(input=times, output=buf.add(values, type_), interpolation="LINEAR")
        )
        anim.channels.append(
            gl.AnimationChannel(
                sampler=len(anim.samplers) - 1,
                target=gl.AnimationChannelTarget(node=node, path=path),
            )
        )

    channel(1, "translation", motion.hips_translation, gl.VEC3)
    rotations = motion.rotations / np.linalg.norm(motion.rotations, axis=-1, keepdims=True)
    for i in range(j):
        channel(i + 1, "rotation", rotations[:, i], gl.VEC4)
    gltf.animations.append(anim)

    gltf.scenes.append(gl.Scene(name=ROOT_NODE, nodes=[0]))
    gltf.scene = 0
    gltf.buffers.append(gl.Buffer(byteLength=len(buf.data)))
    gltf.set_binary_blob(bytes(buf.data))
    return gltf


def run_export(
    library: Path, clip_id: str, *, log: Callable[[str], None] = lambda _m: None
) -> ExportResult:
    """Export one cleaned clip to `motion.glb` and set its status to `exported`."""
    clip = clip_dir(library, clip_id)
    if not (clip / "meta.json").is_file():
        raise ExportError(f"no clip {clip_id} in {library}")
    meta = read_meta(clip)
    src = clip / CLEAN_DIR / MOTION_FILE
    if meta.status not in _READY or not src.is_file():
        raise ExportError(f"clip {clip_id} is not cleaned yet; run `anim8te clean {clip_id}`")

    log(f"loading {src.relative_to(library)}")
    motion = Motion.load(src)
    gltf = build_gltf(motion, meta.id)

    out = clip / GLB_FILE
    tmp = clip / f".{GLB_FILE}.tmp"
    gltf.save_binary(str(tmp))
    os.replace(tmp, out)

    if meta.status != ClipStatus.ready:
        meta.status = ClipStatus.exported
    write_meta(clip, meta)
    return ExportResult(
        clip=clip,
        meta=meta,
        glb=out,
        animation=meta.id,
        num_frames=motion.num_frames,
        fps=motion.fps,
        duration_s=(motion.num_frames - 1) / motion.fps,
        size_bytes=out.stat().st_size,
    )
