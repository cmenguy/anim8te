"""Library data model and on-disk layout (GDD §8.1).

`library/clips/<clip_id>/meta.json` describes one clip from prompt to export; `qc.json` holds
its quality report. `library/performers/<performer_id>/base.png` is the performer's base image.
The models here are the single schema the CLI, the daemon and the Godot app read.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCHEMA_VERSION = 1


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class _Model(BaseModel):
    # Typos in hand-edited JSON fail loudly instead of being dropped.
    model_config = ConfigDict(extra="forbid")


class Template(StrEnum):
    """Prompt template (GDD §7.1 Flow A); decides the camera and treadmill rules."""

    locomotion = "locomotion"
    traversal = "traversal"
    combat = "combat"
    custom = "custom"


class RootMotionMode(StrEnum):
    """How stage 5 produces root motion (GDD §4 stage 5)."""

    none = "none"  # root stays where the hips put it, e.g. idles
    extract = "extract"  # taken from the hips' travel
    synthesize = "synthesize"  # treadmill clips: forward velocity from the target speed


class ClipStatus(StrEnum):
    """Where a clip is in the pipeline. Stages move it forward; `failed` can happen anywhere."""

    new = "new"
    generated = "generated"
    extracted = "extracted"
    cleaned = "cleaned"
    exported = "exported"
    ready = "ready"  # saved to the library by the user (M3)
    failed = "failed"


class Take(_Model):
    """One generated video under `takes/<n>.mp4`."""

    n: int = Field(ge=1)
    seed: int | None = None
    model: str | None = None  # fal endpoint, e.g. "minimax/h3-max/image-to-video"
    duration_s: float = Field(gt=0)
    resolution: str  # "768P", "1080P"
    cost_usd: float | None = Field(default=None, ge=0)
    video_url: str | None = None
    created_at: datetime = Field(default_factory=_now)

    @property
    def filename(self) -> str:
        return f"{self.n}.mp4"


class Filter(_Model):
    """One cleanup filter's toggle and parameters (GDD §4 stage 5.4)."""

    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class Segment(_Model):
    """A named sub-clip of `motion.glb`, in seconds from the start of the cleaned clip."""

    name: str = Field(min_length=1)
    start_s: float = Field(ge=0)
    end_s: float

    @model_validator(mode="after")
    def _ordered(self) -> Segment:
        if self.end_s <= self.start_s:
            raise ValueError(f"segment {self.name!r}: end_s must be after start_s")
        return self


class ClipMeta(_Model):
    """`meta.json`: everything needed to reproduce and describe one clip."""

    schema_version: Literal[1] = SCHEMA_VERSION
    id: str
    name: str
    tags: list[str] = Field(default_factory=list)
    performer: str
    template: Template = Template.custom
    prompt: str  # what the user typed
    final_prompt: str | None = None  # after the template's camera and treadmill rules
    takes: list[Take] = Field(default_factory=list)
    selected_take: int | None = None
    filters: dict[str, Filter] = Field(default_factory=dict)
    segments: list[Segment] = Field(default_factory=list)
    loop: bool = False
    root_motion: RootMotionMode = RootMotionMode.none
    status: ClipStatus = ClipStatus.new
    parent_clip: str | None = None  # set on clips made by extend-video (M3.13)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def _consistent(self) -> ClipMeta:
        numbers = [t.n for t in self.takes]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"duplicate take numbers: {numbers}")
        if self.selected_take is not None and self.selected_take not in numbers:
            raise ValueError(f"selected_take {self.selected_take} is not one of the takes")
        if self.parent_clip == self.id:
            raise ValueError("a clip cannot be its own parent")
        names = [s.name for s in self.segments]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate segment names: {names}")
        return self

    @property
    def total_cost_usd(self) -> float:
        return sum(t.cost_usd or 0.0 for t in self.takes)


class QCStatus(StrEnum):
    pending = "pending"  # not computed yet
    ok = "ok"
    warn = "warn"
    fail = "fail"


class QCReport(_Model):
    """`qc.json`. Placeholder until M3.6 fills in the metrics and thresholds."""

    schema_version: Literal[1] = SCHEMA_VERSION
    status: QCStatus = QCStatus.pending
    metrics: dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    computed_at: datetime | None = None


class ContactThresholds(_Model):
    """The `contacts` filter parameters a `features.json` was computed with."""

    height_m: float
    speed_mps: float
    min_frames: int
    ground_velocity: list[float]  # (x, z) m/s the ground moved at: the belt on a treadmill


class ClipFeatures(_Model):
    """`features.json`: per-frame features of the cleaned clip, written by `anim8te clean`.

    Everything is in the glTF frame (Y-up, metres, the performer facing +Z) after smoothing and
    ground alignment, one entry per frame at `fps`. The Gym overlays and QC read this file
    instead of recomputing, so they agree. Per-frame arrays are indexed `[frame][joint][axis]`
    with joints in `bone_names` order.
    """

    schema_version: Literal[1] = SCHEMA_VERSION
    fps: float
    num_frames: int
    bone_names: list[str]
    # `contacts[bone][frame]` for LeftFoot, RightFoot, LeftToes, RightToes; empty when the
    # contacts filter is off
    contacts: dict[str, list[bool]] = Field(default_factory=dict)
    contact_thresholds: ContactThresholds | None = None
    # rest height of each contact bone above the soles, metres: a joint's sole height is its
    # height minus this (ground penetration, contacts); empty in files written before M2.8
    rest_heights_above_sole: dict[str, float] = Field(default_factory=dict)
    root_position: list[list[float]]  # [frame][axis], the Hips joint, metres
    root_velocity: list[list[float]]  # [frame][axis], m/s
    joint_positions: list[list[list[float]]]  # [frame][joint][axis], metres
    joint_jerk: list[list[float]]  # [frame][joint], magnitude of the third derivative, m/s^3


# --- ids and paths ---------------------------------------------------------------------------

_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:40].rstrip("-") or "clip"


def new_clip_id(name: str) -> str:
    """`<slug>-<6 random chars>`, so re-generating "vault" never collides with an older vault."""
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))
    return f"{slugify(name)}-{suffix}"


def clips_dir(library: Path) -> Path:
    return library / "clips"


def performers_dir(library: Path) -> Path:
    return library / "performers"


def clip_dir(library: Path, clip_id: str) -> Path:
    return clips_dir(library) / clip_id


# --- reading and writing ---------------------------------------------------------------------


def _write_json_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text + "\n")
    os.replace(tmp, path)


def read_meta(clip: Path) -> ClipMeta:
    return ClipMeta.model_validate_json((clip / "meta.json").read_text())


def write_meta(clip: Path, meta: ClipMeta, *, touch: bool = True) -> None:
    """Write `meta.json` atomically; a crash mid-write never leaves a half file behind."""
    if touch:
        meta.updated_at = _now()
    clip.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(clip / "meta.json", meta.model_dump_json(indent=2))


def read_qc(clip: Path) -> QCReport:
    path = clip / "qc.json"
    if not path.is_file():
        return QCReport()
    return QCReport.model_validate_json(path.read_text())


def write_qc(clip: Path, qc: QCReport) -> None:
    clip.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(clip / "qc.json", qc.model_dump_json(indent=2))


def read_features(clip: Path) -> ClipFeatures:
    return ClipFeatures.model_validate_json((clip / "features.json").read_text())


def write_features(clip: Path, features: ClipFeatures) -> None:
    clip.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(clip / "features.json", features.model_dump_json())


# --- listing ---------------------------------------------------------------------------------


class ClipEntry(BaseModel):
    """One row of `lib ls`. `meta` is None when meta.json is missing or invalid (see `error`)."""

    id: str
    path: Path
    meta: ClipMeta | None = None
    qc: QCReport | None = None
    error: str | None = None

    @property
    def status(self) -> str:
        return self.meta.status.value if self.meta else self.error or "unknown"


class PerformerEntry(BaseModel):
    id: str
    path: Path
    has_base_image: bool
    clip_count: int = 0

    @property
    def status(self) -> str:
        return "ok" if self.has_base_image else "missing base.png"


def list_clips(library: Path) -> list[ClipEntry]:
    root = clips_dir(library)
    if not root.is_dir():
        return []
    entries = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        entry = ClipEntry(id=d.name, path=d)
        if not (d / "meta.json").is_file():
            entry.error = "no meta.json"
        else:
            try:
                entry.meta = read_meta(d)
            except (ValidationError, ValueError):
                entry.error = "invalid meta.json"
            try:
                entry.qc = read_qc(d)
            except (ValidationError, ValueError):
                entry.qc = None
        entries.append(entry)
    return entries


def list_performers(library: Path, clips: list[ClipEntry] | None = None) -> list[PerformerEntry]:
    root = performers_dir(library)
    if not root.is_dir():
        return []
    clips = list_clips(library) if clips is None else clips
    counts: dict[str, int] = {}
    for c in clips:
        if c.meta:
            counts[c.meta.performer] = counts.get(c.meta.performer, 0) + 1
    return [
        PerformerEntry(
            id=d.name,
            path=d,
            has_base_image=(d / "base.png").is_file(),
            clip_count=counts.get(d.name, 0),
        )
        for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    ]
