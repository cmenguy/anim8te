import subprocess
from fractions import Fraction
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anim8te import video
from anim8te.cli import app
from anim8te.library import ClipMeta, write_meta
from anim8te.video import VideoError, find_ffmpeg, probe, run_transcode, to_ogv


def _theora_ffmpeg() -> Path:
    try:
        return find_ffmpeg()
    except VideoError as e:
        pytest.skip(f"no ffmpeg with libtheora: {e}")


def _fake_ffmpeg(directory: Path, encoders: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / "ffmpeg"
    exe.write_text(f"#!/bin/sh\ncat <<'END'\n{encoders}\nEND\n")
    exe.chmod(0o755)
    return exe


def _mp4(ffmpeg: Path, path: Path, size: str, rate: int, frames: int) -> Path:
    """A small synthetic test video (with audio, like an H3 Max take)."""
    cmd = [str(ffmpeg), "-v", "error", "-y", "-f", "lavfi", "-i"]
    cmd += [f"testsrc=size={size}:rate={rate}", "-f", "lavfi", "-i", "sine=frequency=440"]
    cmd += ["-frames:v", str(frames), "-shortest", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return path


def test_find_ffmpeg_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(video, "KEG_FFMPEG", ())
    with pytest.raises(VideoError, match="ffmpeg not found.*brew install ffmpeg-full"):
        find_ffmpeg({"PATH": str(tmp_path)})


def test_find_ffmpeg_without_theora(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(video, "KEG_FFMPEG", ())
    _fake_ffmpeg(tmp_path / "bin", " V....D libx264  libx264 H.264")
    with pytest.raises(VideoError, match="no ffmpeg with the libtheora encoder"):
        find_ffmpeg({"PATH": str(tmp_path / "bin")})


def test_find_ffmpeg_prefers_env_then_path_then_keg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    theora = " V....D libtheora  libtheora Theora (codec theora)"
    plain = _fake_ffmpeg(tmp_path / "plain", " V....D libx264  libx264 H.264")
    keg = _fake_ffmpeg(tmp_path / "keg", theora)
    env_ffmpeg = _fake_ffmpeg(tmp_path / "env", theora)
    monkeypatch.setattr(video, "KEG_FFMPEG", (keg,))
    assert find_ffmpeg({"PATH": str(plain.parent)}) == keg  # PATH's lacks theora: keg
    env = {"PATH": str(plain.parent), video.FFMPEG_ENV: str(env_ffmpeg)}
    assert find_ffmpeg(env) == env_ffmpeg


def test_to_ogv_keeps_size_rate_and_frames(tmp_path: Path):
    ffmpeg = _theora_ffmpeg()
    src = _mp4(ffmpeg, tmp_path / "take.mp4", "320x400", 24, 30)
    info = to_ogv(src, tmp_path / "take.ogv", ffmpeg)
    assert (info.codec, info.width, info.height, info.fps, info.frames) == (
        "theora", 320, 400, Fraction(24), 30
    )  # fmt: skip
    assert probe(tmp_path / "take.ogv", ffmpeg) == info
    assert not list(tmp_path.glob(".*"))  # no temp file left


def test_to_ogv_reports_unreadable_input(tmp_path: Path):
    ffmpeg = _theora_ffmpeg()
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(VideoError, match="cannot read a video stream"):
        to_ogv(bad, tmp_path / "bad.ogv", ffmpeg)
    assert not (tmp_path / "bad.ogv").exists()


def test_transcode_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ffmpeg = _theora_ffmpeg()
    clip = tmp_path / "clips" / "walk-abc123"
    (clip / "gvhmr").mkdir(parents=True)
    write_meta(clip, ClipMeta(id="walk-abc123", name="walk", performer="p", prompt="walk"))
    _mp4(ffmpeg, clip / "selected.mp4", "160x200", 24, 24)
    _mp4(ffmpeg, clip / "gvhmr" / "overlay.mp4", "160x100", 30, 30)

    written = run_transcode(tmp_path, "walk-abc123")
    assert {p.relative_to(clip).as_posix(): i.frames for p, i in written.items()} == {
        "selected.ogv": 24,
        "gvhmr/overlay.ogv": 30,
    }
    with pytest.raises(VideoError, match="no clip nope"):
        run_transcode(tmp_path, "nope")

    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "transcode", "walk-abc123"])
    assert r.exit_code == 0, r.output
    assert "selected.ogv" in r.output
