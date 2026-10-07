"""Stage 5.3: the canonical skeleton (GDD §4 stage 5).

Every library clip uses the same skeleton: the 22 SMPL-X body joints, in SMPL-X order, renamed with
Godot's `SkeletonProfileHumanoid` bone names so Godot's importer auto-detects the bone map. No
fingers, jaw or eyes.

The rest pose is the SMPL-X zero pose with the performer's body shape (`betas`), so GVHMR's
parent-relative rotations apply to it unchanged: every bone's rest rotation is the identity and its
rest translation is the offset from its parent joint. Godot's humanoid retarget absorbs the
difference to a model's own rest pose.

Per G0 the body shape belongs to the performer, not the clip: GVHMR fits a slightly different shape
on every take (M0.7 measured a 6 cm stature spread), so the first clip's `betas` are stored once in
`library/performers/<id>/betas.json` and every later clip of that performer reuses them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from anim8te.convert import BODY_JOINT_NAMES, NUM_BETAS, rest_skeleton
from anim8te.library import _write_json_atomic, performers_dir

# SMPL-X body joint -> SkeletonProfileHumanoid bone (GDD §4 stage 5 table)
SMPLX_TO_HUMANOID: dict[str, str] = {
    "pelvis": "Hips",
    "spine1": "Spine",
    "spine2": "Chest",
    "spine3": "UpperChest",
    "neck": "Neck",
    "head": "Head",
    "left_hip": "LeftUpperLeg",
    "right_hip": "RightUpperLeg",
    "left_knee": "LeftLowerLeg",
    "right_knee": "RightLowerLeg",
    "left_ankle": "LeftFoot",
    "right_ankle": "RightFoot",
    "left_foot": "LeftToes",
    "right_foot": "RightToes",
    "left_collar": "LeftShoulder",
    "right_collar": "RightShoulder",
    "left_shoulder": "LeftUpperArm",
    "right_shoulder": "RightUpperArm",
    "left_elbow": "LeftLowerArm",
    "right_elbow": "RightLowerArm",
    "left_wrist": "LeftHand",
    "right_wrist": "RightHand",
}

# Canonical bone names, index-aligned with the SMPL-X joints (and GVHMR's body_pose + 1)
BONE_NAMES: tuple[str, ...] = tuple(SMPLX_TO_HUMANOID[j] for j in BODY_JOINT_NAMES)

# SMPL-X kinematic tree for the 22 body joints, -1 for the root (smplx `model.parents`)
PARENTS: tuple[int, ...] = (
    -1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19,
)  # fmt: skip

ROOT = "Hips"
BETAS_FILE = "betas.json"


@dataclass(frozen=True)
class CanonicalSkeleton:
    """The canonical skeleton with one body shape in rest pose.

    Positions are in the SMPL-X model frame, which is already glTF's at rest: Y-up, right-handed,
    metres, facing +Z, the performer's left at +X. Rest rotations are all the identity.
    """

    rest_positions: np.ndarray  # (22, 3) joint positions, metres
    betas: np.ndarray  # (10,) the shape they were built from
    names: tuple[str, ...] = BONE_NAMES
    parents: tuple[int, ...] = PARENTS

    def rest_offsets(self) -> np.ndarray:
        """(22, 3) each bone's rest translation from its parent; Hips keeps its position."""
        out = self.rest_positions.copy()
        idx = np.asarray(self.parents[1:])
        out[1:] -= self.rest_positions[idx]
        return out

    def index(self, name: str) -> int:
        return self.names.index(name)

    def children(self, i: int) -> list[int]:
        return [c for c, p in enumerate(self.parents) if p == i]


def canonical_skeleton(betas: np.ndarray, body_models: Path | None = None) -> CanonicalSkeleton:
    """Build the canonical skeleton's rest pose from a performer's `betas` (SMPL-X, neutral)."""
    betas = np.asarray(betas, dtype=np.float32).reshape(NUM_BETAS)
    rest = rest_skeleton(betas, body_models=body_models)
    if tuple(rest.parents.tolist()) != PARENTS:
        raise ValueError(f"unexpected SMPL-X parent table: {rest.parents.tolist()}")
    return CanonicalSkeleton(rest_positions=rest.joints, betas=betas)


# --- performer body shape ------------------------------------------------------------------


def performer_betas_path(library: Path, performer: str) -> Path:
    return performers_dir(library) / performer / BETAS_FILE


def read_performer_betas(library: Path, performer: str) -> np.ndarray | None:
    """The performer's stored `betas`, or None if no clip has set them yet."""
    path = performer_betas_path(library, performer)
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    betas = np.asarray(data["betas"], dtype=np.float32)
    if betas.shape != (NUM_BETAS,):
        raise ValueError(f"{path}: expected {NUM_BETAS} betas, got shape {betas.shape}")
    return betas


def performer_betas(
    library: Path, performer: str, clip_betas: np.ndarray, source_clip: str
) -> np.ndarray:
    """The performer's body shape: the stored one, else `clip_betas`, stored for later clips.

    The first clip extracted for a performer fixes the shape; later clips' own `betas` are ignored
    here (QC compares them against the stored reference, M3.5).
    """
    stored = read_performer_betas(library, performer)
    if stored is not None:
        return stored
    betas = np.asarray(clip_betas, dtype=np.float32).reshape(NUM_BETAS)
    path = performer_betas_path(library, performer)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"betas": betas.tolist(), "model": "smplx-neutral", "source_clip": source_clip}
    _write_json_atomic(path, json.dumps(payload, indent=2))
    return betas
