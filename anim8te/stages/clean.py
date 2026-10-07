"""Stage 5.4 (minimal): smoothing and ground alignment (GDD §4 stage 5).

`run_clean` reads the raw GVHMR output in `gvhmr/hmr4d_results.pt`, puts it on the canonical
skeleton in the glTF frame, smooths it and moves it onto the ground, then writes
`clean/motion.npz` for `anim8te export`. It always starts from the raw output, never from a
previous `clean/`, so re-running with the same filters gives the same result.

Filters live in `meta.json` under `filters`, one entry per filter with `enabled` and `params`:

- `smooth`: Savitzky-Golay over time on every bone's rotation (unit quaternions kept in one
  hemisphere, then renormalised) and on the Hips translation. `window` frames (odd), polynomial
  `order`. GVHMR output is 30 fps, so the default 9-frame window spans 0.3 s.
- `ground`: per frame, the lowest sole over the feet and toes, estimated from each joint's height
  minus its rest-pose height above the soles; the clip's `percentile` of that is moved to y = 0.
  A low percentile rather than the minimum, so one bad frame does not lift the whole clip.
- `contacts`: foot and toe contact detection for `features.json` (see `anim8te.stages.features`
  for the parameters). It changes no motion; foot locking is M3.1.

Every run also writes `features.json` (per-frame contacts, root track, joint positions, jerk)
from the cleaned motion.

Missing filters and parameters are filled with the defaults and written back, so `meta.json`
always shows what was applied. Foot lock, root motion, loop, segmentation and QC come later (M3).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from anim8te.convert import (
    GvhmrParams,
    axis_angle_to_matrix,
    load_gvhmr,
    rest_skeleton,
    to_gltf_frame,
)
from anim8te.library import (
    ClipMeta,
    ClipStatus,
    Filter,
    clip_dir,
    read_meta,
    write_features,
    write_meta,
)
from anim8te.skeleton import BONE_NAMES, PARENTS, canonical_skeleton, performer_betas
from anim8te.stages.features import CONTACT_BONES, DEFAULT_CONTACTS, compute_features

CLEAN_DIR = "clean"
MOTION_FILE = "motion.npz"
GVHMR_RESULT = Path("gvhmr") / "hmr4d_results.pt"

DEFAULT_FILTERS: dict[str, dict[str, Any]] = {
    "smooth": {"method": "savgol", "window": 9, "order": 3},
    "ground": {"percentile": 5.0},
    "contacts": DEFAULT_CONTACTS,
}
FOOT_BONES = CONTACT_BONES

_READY = {ClipStatus.extracted, ClipStatus.cleaned, ClipStatus.exported, ClipStatus.ready}


class CleanError(Exception):
    """Anything that stops a clean; the message is meant for the user as is."""


class CleanResult(BaseModel):
    clip: Path
    meta: ClipMeta
    motion: Path
    features: Path
    contact_frames: dict[str, int]  # frames in contact per foot joint; empty when contacts off
    num_frames: int
    fps: float
    ground_offset_m: float | None  # how far the clip was lowered (negative: raised)


# --- filters ---------------------------------------------------------------------------------


def savgol(x: np.ndarray, window: int, order: int) -> np.ndarray:
    """Savitzky-Golay filter along axis 0 of `x` (T, ...).

    Interior frames use the centred least-squares polynomial; the first and last `window // 2`
    frames evaluate the polynomial fitted to the first or last full window (scipy's "interp"
    mode). A window longer than the clip shrinks to the longest odd length that fits.
    """
    x = np.asarray(x, dtype=np.float64)
    t = x.shape[0]
    window = min(window, t if t % 2 else t - 1)
    if window <= order:
        return x.copy()
    h = window // 2
    offsets = np.arange(-h, h + 1, dtype=np.float64)
    vander = offsets[:, None] ** np.arange(order + 1)  # (w, p+1)
    fit = np.linalg.pinv(vander)  # (p+1, w): window samples -> polynomial coefficients
    centre = fit[0]  # value at offset 0

    flat = x.reshape(t, -1)
    out = np.empty_like(flat)
    interior = np.zeros((t - 2 * h, flat.shape[1]))
    for k in range(window):
        interior += centre[k] * flat[k : t - 2 * h + k]
    out[h : t - h] = interior
    edge = vander[:h] @ fit  # (h, w): first window -> its first h frames
    out[:h] = edge @ flat[:window]
    out[t - h :] = (vander[h + 1 :] @ fit) @ flat[t - window :]
    return out.reshape(x.shape)


def matrix_to_quaternion(m: np.ndarray) -> np.ndarray:
    """(..., 3, 3) rotation matrices to (..., 4) unit quaternions, glTF order (x, y, z, w)."""
    m = np.asarray(m, dtype=np.float64)
    tr = np.trace(m, axis1=-2, axis2=-1)
    # the four candidate magnitudes; pick the largest per rotation for stability
    w2 = np.stack(
        [
            1 + m[..., 0, 0] - m[..., 1, 1] - m[..., 2, 2],
            1 - m[..., 0, 0] + m[..., 1, 1] - m[..., 2, 2],
            1 - m[..., 0, 0] - m[..., 1, 1] + m[..., 2, 2],
            1 + tr,
        ],
        axis=-1,
    )
    best = np.argmax(w2, axis=-1)
    s = np.sqrt(np.maximum(np.take_along_axis(w2, best[..., None], -1)[..., 0], 1e-12)) * 2
    a = m[..., 2, 1] - m[..., 1, 2]
    b = m[..., 0, 2] - m[..., 2, 0]
    c = m[..., 1, 0] - m[..., 0, 1]
    xy = m[..., 0, 1] + m[..., 1, 0]
    xz = m[..., 0, 2] + m[..., 2, 0]
    yz = m[..., 1, 2] + m[..., 2, 1]
    cand = np.stack(
        [
            np.stack([s / 4, xy / s, xz / s, a / s], -1),
            np.stack([xy / s, s / 4, yz / s, b / s], -1),
            np.stack([xz / s, yz / s, s / 4, c / s], -1),
            np.stack([a / s, b / s, c / s, s / 4], -1),
        ],
        axis=-2,
    )
    q = np.take_along_axis(cand, best[..., None, None], -2)[..., 0, :]
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def quaternion_to_matrix(q: np.ndarray) -> np.ndarray:
    """(..., 4) quaternions (x, y, z, w) to (..., 3, 3) rotation matrices."""
    q = np.asarray(q, dtype=np.float64)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    return np.stack(
        [
            1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
            2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
            2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y),
        ],
        axis=-1,
    ).reshape(q.shape[:-1] + (3, 3))  # fmt: skip


def continuous_quaternions(q: np.ndarray) -> np.ndarray:
    """Flip signs along axis 0 so consecutive quaternions sit in the same hemisphere."""
    q = np.array(q, dtype=np.float64)
    for i in range(1, q.shape[0]):
        flip = (q[i] * q[i - 1]).sum(-1) < 0
        q[i][flip] *= -1
    return q


def smooth_quaternions(q: np.ndarray, window: int, order: int) -> np.ndarray:
    """Savitzky-Golay on (T, ..., 4) unit quaternions, renormalised; signs made continuous."""
    out = savgol(continuous_quaternions(q), window, order)
    return out / np.linalg.norm(out, axis=-1, keepdims=True)


def forward_kinematics(
    rotations: np.ndarray, hips: np.ndarray, offsets: np.ndarray, parents: tuple[int, ...]
) -> np.ndarray:
    """World joint positions (T, J, 3) from local rotation matrices (T, J, 3, 3), the Hips
    translation (T, 3) and rest offsets (J, 3). Parents must come before children."""
    t, j = rotations.shape[:2]
    world_rot = np.empty((t, j, 3, 3))
    pos = np.empty((t, j, 3))
    world_rot[:, 0], pos[:, 0] = rotations[:, 0], hips
    for i in range(1, j):
        p = parents[i]
        world_rot[:, i] = world_rot[:, p] @ rotations[:, i]
        pos[:, i] = pos[:, p] + world_rot[:, p] @ offsets[i]
    return pos


def ground_offset(sole_heights: np.ndarray, percentile: float) -> float:
    """The clip's ground height: `percentile` of the per-frame lowest sole (T, n_feet)."""
    return float(np.percentile(np.asarray(sole_heights).min(axis=1), percentile))


# --- meta.json filters -----------------------------------------------------------------------


def resolve_filters(meta: ClipMeta) -> dict[str, Filter]:
    """The clip's `smooth`, `ground` and `contacts` filters with defaults filled in; other
    filters kept."""
    filters = dict(meta.filters)
    for name, defaults in DEFAULT_FILTERS.items():
        f = filters.get(name, Filter())
        unknown = sorted(set(f.params) - set(defaults))
        if unknown:
            raise CleanError(
                f"filters.{name}: unknown parameter(s) {', '.join(unknown)} "
                f"(known: {', '.join(defaults)})"
            )
        filters[name] = Filter(enabled=f.enabled, params={**defaults, **f.params})

    sp = filters["smooth"].params
    if sp["method"] != "savgol":
        raise CleanError(f"filters.smooth.method {sp['method']!r}: only 'savgol' is supported")
    window, order = sp["window"], sp["order"]
    if not (isinstance(window, int) and window >= 3 and window % 2 == 1):
        raise CleanError(f"filters.smooth.window must be an odd integer >= 3, got {window!r}")
    if not (isinstance(order, int) and 0 <= order < window):
        raise CleanError(f"filters.smooth.order must be an integer in [0, window), got {order!r}")
    pct = filters["ground"].params["percentile"]
    if not (isinstance(pct, int | float) and 0 <= pct <= 100):
        raise CleanError(f"filters.ground.percentile must be in [0, 100], got {pct!r}")
    cp = filters["contacts"].params
    for key in ("height_m", "speed_mps"):
        if not (isinstance(cp[key], int | float) and cp[key] > 0):
            raise CleanError(f"filters.contacts.{key} must be a number > 0, got {cp[key]!r}")
    if not (isinstance(cp["min_frames"], int) and cp["min_frames"] >= 1):
        raise CleanError(
            f"filters.contacts.min_frames must be an integer >= 1, got {cp['min_frames']!r}"
        )
    gv = cp["ground_velocity"]
    if not (
        gv == "auto"
        or (isinstance(gv, list) and len(gv) == 2 and all(isinstance(v, int | float) for v in gv))
    ):
        raise CleanError(
            f'filters.contacts.ground_velocity must be "auto" or [x, z] in m/s, got {gv!r}'
        )
    return filters


# --- the stage -------------------------------------------------------------------------------


def clean_motion(
    params: GvhmrParams,
    rest_offsets: np.ndarray,
    rest_heights_above_sole: np.ndarray,
    pelvis_rest: np.ndarray,
    filters: dict[str, Filter],
) -> tuple[np.ndarray, np.ndarray, float | None]:
    """Canonical-skeleton motion in the glTF frame, smoothed and grounded.

    `rest_offsets` (22, 3) are the canonical skeleton's; `rest_heights_above_sole` (4,) are the
    FOOT_BONES' rest heights above the soles; `pelvis_rest` (3,) is the pelvis rest position for
    the clip's own `betas`, which with `transl` gives the pelvis world track.
    Returns rotations (T, 22, 4) as quaternions (x, y, z, w), the Hips translation (T, 3) and
    the ground offset that was removed (None when the ground filter is off).
    """
    # SMPL-X rotates the body about the pelvis rest joint, then adds transl: pelvis = J0 + transl
    pelvis_world = params.transl.astype(np.float64) + pelvis_rest
    hips, root_aa = to_gltf_frame(pelvis_world, params.global_orient.astype(np.float64))
    local_aa = np.concatenate([root_aa[:, None], params.body_pose.astype(np.float64)], axis=1)
    quats = continuous_quaternions(matrix_to_quaternion(axis_angle_to_matrix(local_aa)))
    hips = hips.astype(np.float64)

    smooth = filters["smooth"]
    if smooth.enabled:
        quats = smooth_quaternions(quats, smooth.params["window"], smooth.params["order"])
        hips = savgol(hips, smooth.params["window"], smooth.params["order"])

    offset = None
    ground = filters["ground"]
    if ground.enabled:
        pos = forward_kinematics(quaternion_to_matrix(quats), hips, rest_offsets, PARENTS)
        feet = [BONE_NAMES.index(b) for b in FOOT_BONES]
        soles = pos[:, feet, 1] - rest_heights_above_sole
        offset = ground_offset(soles, ground.params["percentile"])
        hips = hips - np.array([0.0, offset, 0.0])
    return quats.astype(np.float32), hips.astype(np.float32), offset


def run_clean(
    library: Path,
    clip_id: str,
    *,
    toggles: dict[str, bool] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
    body_models: Path | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> CleanResult:
    """Clean one extracted clip: write `clean/motion.npz`, the filters and status `cleaned`.

    `toggles` ({filter: enabled}) and `overrides` ({filter: {param: value}}) are applied to the
    clip's filters in `meta.json` before cleaning and saved with them.
    """
    clip = clip_dir(library, clip_id)
    if not (clip / "meta.json").is_file():
        raise CleanError(f"no clip {clip_id} in {library}")
    meta = read_meta(clip)
    raw = clip / GVHMR_RESULT
    if meta.status not in _READY or not raw.is_file():
        raise CleanError(f"clip {clip_id} is not extracted yet; run `anim8te extract {clip_id}`")

    for name, enabled in (toggles or {}).items():
        f = meta.filters.get(name, Filter())
        meta.filters[name] = Filter(enabled=enabled, params=f.params)
    for name, params in (overrides or {}).items():
        f = meta.filters.get(name, Filter())
        meta.filters[name] = Filter(enabled=f.enabled, params={**f.params, **params})
    filters = resolve_filters(meta)

    log(f"loading {raw.relative_to(library)}")
    params = load_gvhmr(raw)
    betas = performer_betas(library, meta.performer, params.betas, source_clip=meta.id)
    try:
        skel = canonical_skeleton(betas, body_models=body_models)
        pelvis_rest = rest_skeleton(params.betas, body_models=body_models).joints[0]
    except FileNotFoundError as e:
        raise CleanError(str(e)) from e
    feet = [skel.index(b) for b in FOOT_BONES]
    above_sole = skel.rest_positions[feet, 1] - skel.sole_y

    quats, hips, offset = clean_motion(
        params, skel.rest_offsets(), above_sole, pelvis_rest, filters
    )

    out_dir = clip / CLEAN_DIR
    out_dir.mkdir(exist_ok=True)
    motion = out_dir / MOTION_FILE
    tmp = out_dir / f".{MOTION_FILE}.tmp.npz"
    np.savez(
        tmp,
        bone_names=np.array(skel.names),
        parents=np.array(skel.parents, dtype=np.int64),
        rest_offsets=skel.rest_offsets().astype(np.float32),
        rotations=quats,
        hips_translation=hips,
        fps=np.float32(params.fps),
        betas=skel.betas,
        sole_y=np.float32(skel.sole_y),
    )
    os.replace(tmp, motion)

    positions = forward_kinematics(
        quaternion_to_matrix(quats), hips, skel.rest_offsets(), skel.parents
    )
    contacts = filters["contacts"]
    features = compute_features(
        positions,
        list(skel.names),
        above_sole,
        params.fps,
        contacts.params if contacts.enabled else None,
    )
    write_features(clip, features)

    meta.filters = filters
    meta.status = ClipStatus.cleaned
    write_meta(clip, meta)
    return CleanResult(
        clip=clip,
        meta=meta,
        motion=motion,
        features=clip / "features.json",
        contact_frames={b: sum(c) for b, c in features.contacts.items()},
        num_frames=params.num_frames,
        fps=params.fps,
        ground_offset_m=offset,
    )
