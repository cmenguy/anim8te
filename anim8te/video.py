"""Ogg Theora copies of a clip's videos for the Godot app (M2.9, decision Q6).

Godot 4 decodes only Ogg Theora (`VideoStreamTheora`), so Compare mode and the take cards play
`.ogv` copies of `selected.mp4` and `gvhmr/overlay.mp4`, written next to them. The mp4 files
stay the source of truth; the copies are video only (no audio), same size, frame rate and
frame count.

Encoding needs an ffmpeg built with libtheora. Homebrew's `ffmpeg` is not; its keg-only
`ffmpeg-full` is (`brew install ffmpeg-full`) and is found without touching PATH.
`ANIM8TE_FFMPEG` points at any other build.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from anim8te.library import clip_dir

FFMPEG_ENV = "ANIM8TE_FFMPEG"
# Homebrew's keg-only build with libtheora, on Apple Silicon and Intel
KEG_FFMPEG = (
    Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"),
    Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg"),
)
# libtheora quality 0-10; 7 keeps the takes sharp at about a third of the mp4's size
THEORA_QUALITY = 7
# source mp4 -> its Ogg Theora copy, relative to the clip directory
CLIP_VIDEOS = {
    Path("selected.mp4"): Path("selected.ogv"),
    Path("gvhmr/overlay.mp4"): Path("gvhmr/overlay.ogv"),
}


class VideoError(Exception):
    """Anything that stops a transcode; the message is meant for the user as is."""


@dataclass(frozen=True)
class VideoInfo:
    codec: str
    width: int
    height: int
    fps: Fraction
    frames: int


def find_ffmpeg(env: dict[str, str] | None = None) -> Path:
    """An ffmpeg with the libtheora encoder: `ANIM8TE_FFMPEG`, then PATH, then ffmpeg-full."""
    env = os.environ if env is None else env
    candidates: list[Path] = []
    if env.get(FFMPEG_ENV):
        candidates.append(Path(env[FFMPEG_ENV]))
    on_path = shutil.which("ffmpeg", path=env.get("PATH"))
    if on_path:
        candidates.append(Path(on_path))
    candidates.extend(KEG_FFMPEG)
    found = [c for c in candidates if c.is_file()]
    for ffmpeg in found:
        if _has_theora(ffmpeg):
            return ffmpeg
    if found:
        tried = ", ".join(str(c) for c in found)
        raise VideoError(
            f"no ffmpeg with the libtheora encoder (tried {tried}); Homebrew's ffmpeg lacks it: "
            f"`brew install ffmpeg-full`, or set {FFMPEG_ENV} to a build that has it"
        )
    raise VideoError(
        "ffmpeg not found; it is needed to write the .ogv copies Godot plays: "
        f"`brew install ffmpeg-full`, or set {FFMPEG_ENV}"
    )


def _has_theora(ffmpeg: Path) -> bool:
    try:
        out = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.split()[1:2] == ["libtheora"] for line in out.splitlines())


def probe(path: Path, ffmpeg: Path) -> VideoInfo:
    """First video stream of `path`, frames counted by decoding (Ogg has no frame count)."""
    ffprobe = ffmpeg.with_name("ffprobe")
    if not ffprobe.is_file():
        raise VideoError(f"no ffprobe next to {ffmpeg}")
    cmd = [str(ffprobe), "-v", "error", "-count_frames", "-select_streams", "v:0"]
    cmd += ["-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_read_frames"]
    cmd += ["-of", "json", str(path)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    streams = json.loads(run.stdout or "{}").get("streams") if run.returncode == 0 else None
    if not streams:
        raise VideoError(f"cannot read a video stream from {path}: {run.stderr.strip()}")
    s = streams[0]
    return VideoInfo(
        codec=s["codec_name"],
        width=s["width"],
        height=s["height"],
        fps=Fraction(s["r_frame_rate"]),
        frames=int(s["nb_read_frames"]),
    )


def to_ogv(src: Path, dest: Path, ffmpeg: Path) -> VideoInfo:
    """Writes `dest`, an Ogg Theora copy of `src`'s video; checks it kept size, rate and frames."""
    want = probe(src, ffmpeg)
    tmp = dest.with_name(f".{dest.stem}.tmp.ogv")
    cmd = [str(ffmpeg), "-v", "error", "-y", "-i", str(src), "-map", "0:v:0", "-an"]
    cmd += ["-c:v", "libtheora", "-q:v", str(THEORA_QUALITY), "-pix_fmt", "yuv420p", str(tmp)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise VideoError(f"ffmpeg could not transcode {src}: {run.stderr.strip()}")
    got = probe(tmp, ffmpeg)
    if (got.width, got.height, got.fps, got.frames) != (
        want.width,
        want.height,
        want.fps,
        want.frames,
    ):
        tmp.unlink(missing_ok=True)
        raise VideoError(
            f"{dest.name} came out {got.width}x{got.height} at {got.fps} fps, {got.frames} "
            f"frames; {src.name} is {want.width}x{want.height} at {want.fps} fps, "
            f"{want.frames} frames"
        )
    os.replace(tmp, dest)
    return got


def transcode_clip(
    clip: Path, ffmpeg: Path | None = None, log=lambda _: None
) -> dict[Path, VideoInfo]:
    """Writes the `.ogv` copy of each of the clip's videos (CLIP_VIDEOS) that exists."""
    ffmpeg = ffmpeg or find_ffmpeg()
    out: dict[Path, VideoInfo] = {}
    for src_rel, dest_rel in CLIP_VIDEOS.items():
        src = clip / src_rel
        if not src.is_file():
            continue
        info = to_ogv(src, clip / dest_rel, ffmpeg)
        log(f"{dest_rel}: {info.width}x{info.height}, {info.fps} fps, {info.frames} frames")
        out[clip / dest_rel] = info
    return out


def run_transcode(library: Path, clip_id: str, log=lambda _: None) -> dict[Path, VideoInfo]:
    """`anim8te transcode`: the .ogv copies for a clip that was extracted before M2.9."""
    clip = clip_dir(library, clip_id)
    if not (clip / "meta.json").is_file():
        raise VideoError(f"no clip {clip_id} in {library}")
    if not any((clip / src).is_file() for src in CLIP_VIDEOS):
        raise VideoError(f"clip {clip_id} has no selected.mp4 or overlay; run `anim8te extract`")
    return transcode_clip(clip, log=log)
