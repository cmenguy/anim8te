"""Per-frame features of a cleaned clip: contacts, root track, joint positions, jerk.

`anim8te clean` writes them to `features.json` (GDD §4 stage 5.4, §6.4) so the Gym overlays,
QC and segmentation read the same numbers instead of each recomputing them.

Contacts are detected per foot joint (LeftFoot, RightFoot, LeftToes, RightToes) with the
`contacts` filter in `meta.json`:

- `height_m`: the joint's sole height (its height minus its rest height above the soles, as in
  ground alignment) must be under this.
- `speed_mps`: its horizontal speed relative to the ground must be under this. On a treadmill
  the ground is the belt, so a planted foot slides back at belt speed in world space;
  `ground_velocity` "auto" estimates that velocity as the median horizontal velocity of the
  lowest foot joint over the clip (about zero for clips that are not on a treadmill), or takes
  an explicit `[x, z]` in m/s.
- `min_frames`: contact runs shorter than this are dropped as flicker.

Detection only: foot locking during contacts is M3.1.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from anim8te.library import ClipFeatures, ContactThresholds

CONTACT_BONES = ("LeftFoot", "RightFoot", "LeftToes", "RightToes")
DEFAULT_CONTACTS: dict[str, Any] = {
    "height_m": 0.04,
    "speed_mps": 0.8,
    "min_frames": 3,
    "ground_velocity": "auto",
}


def derivative(x: np.ndarray, fps: float, order: int = 1) -> np.ndarray:
    """`order`-th time derivative along axis 0 (central differences, one-sided at the ends)."""
    out = np.asarray(x, dtype=np.float64)
    for _ in range(order):
        out = np.gradient(out, axis=0) * fps if out.shape[0] > 1 else np.zeros_like(out)
    return out


def estimate_ground_velocity(sole_heights: np.ndarray, velocities: np.ndarray) -> np.ndarray:
    """(x, z) ground velocity: the median horizontal velocity of the lowest joint per frame.

    `sole_heights` is (T, n) and `velocities` (T, n, 3) for the contact joints. Some joint is
    on the ground in most frames of a clip, so the lowest one moves with the ground.
    """
    lowest = np.argmin(sole_heights, axis=1)
    v = velocities[np.arange(len(lowest)), lowest][:, [0, 2]]
    return np.median(v, axis=0)


def drop_short_runs(mask: np.ndarray, min_frames: int) -> np.ndarray:
    """Clear runs of True shorter than `min_frames` along axis 0 of a (T, n) mask."""
    out = mask.copy()
    for j in range(mask.shape[1]):
        col = np.concatenate([[False], mask[:, j], [False]]).astype(np.int8)
        edges = np.flatnonzero(np.diff(col))
        for start, end in zip(edges[::2], edges[1::2], strict=True):
            if end - start < min_frames:
                out[start:end, j] = False
    return out


def detect_contacts(
    sole_heights: np.ndarray, velocities: np.ndarray, params: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    """Contact mask (T, n) and the (x, z) ground velocity used.

    `sole_heights` (T, n) are the contact joints' heights above their rest sole height and
    `velocities` (T, n, 3) their velocities, both in metres and m/s, y up.
    """
    gv = params["ground_velocity"]
    if gv == "auto":
        ground = estimate_ground_velocity(sole_heights, velocities)
    else:
        ground = np.asarray(gv, dtype=np.float64)
    rel = velocities[..., [0, 2]] - ground
    speed = np.linalg.norm(rel, axis=-1)
    mask = (sole_heights < params["height_m"]) & (speed < params["speed_mps"])
    return drop_short_runs(mask, params["min_frames"]), ground


def _round(x: np.ndarray, decimals: int) -> list:
    return np.round(np.asarray(x, dtype=np.float64), decimals).tolist()


def compute_features(
    positions: np.ndarray,
    bone_names: list[str],
    rest_heights_above_sole: np.ndarray,
    fps: float,
    contacts: dict[str, Any] | None,
) -> ClipFeatures:
    """Features from world joint positions (T, J, 3) in the glTF frame, grounded.

    `rest_heights_above_sole` (4,) are the CONTACT_BONES' rest heights above the soles;
    `contacts` is the resolved filter's params, or None when the filter is off.
    """
    positions = np.asarray(positions, dtype=np.float64)
    velocity = derivative(positions, fps)
    jerk = np.linalg.norm(derivative(positions, fps, order=3), axis=-1)

    contact_lists: dict[str, list[bool]] = {}
    thresholds = None
    if contacts is not None:
        idx = [bone_names.index(b) for b in CONTACT_BONES]
        heights = positions[:, idx, 1] - np.asarray(rest_heights_above_sole)
        mask, ground = detect_contacts(heights, velocity[:, idx], contacts)
        contact_lists = {b: mask[:, k].tolist() for k, b in enumerate(CONTACT_BONES)}
        thresholds = ContactThresholds(
            height_m=contacts["height_m"],
            speed_mps=contacts["speed_mps"],
            min_frames=contacts["min_frames"],
            ground_velocity=_round(ground, 4),
        )

    return ClipFeatures(
        fps=fps,
        num_frames=positions.shape[0],
        bone_names=list(bone_names),
        contacts=contact_lists,
        contact_thresholds=thresholds,
        root_position=_round(positions[:, 0], 4),
        root_velocity=_round(velocity[:, 0], 4),
        joint_positions=_round(positions, 4),
        joint_jerk=_round(jerk, 2),
    )
