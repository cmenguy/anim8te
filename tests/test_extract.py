import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from anim8te.cli import app
from anim8te.library import ClipMeta, ClipStatus, Take, read_meta, write_meta
from anim8te.stages.extract import ExtractError, WorkerClient, choose_take, run_extract
from anim8te.video import VideoError

TOKEN = "secret"
CLIP = "walk-abc123"


def make_clip(library: Path, takes: list[int], selected: int | None = None) -> Path:
    clip = library / "clips" / CLIP
    (clip / "takes").mkdir(parents=True)
    for n in takes:
        (clip / "takes" / f"{n}.mp4").write_bytes(f"take {n}".encode())
    meta = ClipMeta(
        id=CLIP,
        name="walk",
        performer="perf01",
        prompt="walk",
        takes=[Take(n=n, duration_s=5, resolution="768P") for n in takes],
        selected_take=selected,
        status=ClipStatus.generated,
    )
    write_meta(clip, meta)
    return clip


class FakeWorker:
    """Answers like gvhmr-worker. `statuses` is what successive GET /jobs/{id} calls return."""

    def __init__(self, statuses: list[str] | None = None, error: str | None = None) -> None:
        self.statuses = statuses or ["queued", "running", "done"]
        self.error = error
        self.uploads: list[tuple[bytes, bytes]] = []
        self.polls = 0
        self.fail_download: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "bad or missing token"})
        path = request.url.path
        if request.method == "POST" and path == "/extract":
            self.uploads.append((request.read(), request.headers["content-type"].encode()))
            return httpx.Response(202, json={"job_id": "job1", "status": "queued"})
        if path == "/jobs/job1":
            status = self.statuses[min(self.polls, len(self.statuses) - 1)]
            self.polls += 1
            return httpx.Response(
                200,
                json={
                    "job_id": "job1",
                    "status": status,
                    "error": self.error if status == "failed" else None,
                    "log_tail": [f"step {self.polls}"],
                    "files": {},
                },
            )
        if path.startswith("/jobs/job1/files/"):
            name = path.rsplit("/", 1)[1]
            if name == self.fail_download:
                return httpx.Response(404, json={"detail": f"no file {name}"})
            return httpx.Response(200, content=f"contents of {name}".encode())
        return httpx.Response(404, json={"detail": "not found"})

    def client(self, token: str = TOKEN) -> WorkerClient:
        return WorkerClient("http://worker", token, transport=httpx.MockTransport(self.handler))


def fake_ogv(src: Path, dest: Path, ffmpeg: Path) -> None:
    """Stands in for anim8te.video.to_ogv: the worker's files here are not real videos."""
    dest.write_bytes(b"ogv of " + src.read_bytes())


def run(library: Path, worker: FakeWorker, **kwargs):
    logs: list[str] = []
    kwargs.setdefault("ffmpeg", Path("/fake/ffmpeg"))
    kwargs.setdefault("transcode", fake_ogv)
    result = run_extract(
        library, CLIP, worker.client(), sleep=lambda _: None, log=logs.append, **kwargs
    )
    return result, logs


def test_choose_take():
    meta = ClipMeta(
        id="c", name="c", performer="p", prompt="p",
        takes=[Take(n=n, duration_s=5, resolution="768P") for n in (1, 2)],
    )  # fmt: skip
    assert choose_take(meta, 2) == 2
    with pytest.raises(ExtractError, match="pick one with --take"):
        choose_take(meta, None)
    with pytest.raises(ExtractError, match="no take 3"):
        choose_take(meta, 3)
    meta.selected_take = 1
    assert choose_take(meta, None) == 1
    with pytest.raises(ExtractError, match="no takes"):
        choose_take(ClipMeta(id="c", name="c", performer="p", prompt="p"), None)


def test_extract_happy_path(tmp_path: Path):
    clip = make_clip(tmp_path, [1, 2, 3])
    worker = FakeWorker()
    result, logs = run(tmp_path, worker, take=2)

    assert result.take == 2 and result.job_id == "job1"
    assert (clip / "selected.mp4").read_bytes() == b"take 2"
    assert b"take 2" in worker.uploads[0][0]
    assert b'name="static_camera"' in worker.uploads[0][0]
    for name in ("hmr4d_results.pt", "overlay.mp4"):
        assert (clip / "gvhmr" / name).read_bytes() == f"contents of {name}".encode()
    assert (clip / "selected.ogv").read_bytes() == b"ogv of take 2"
    assert (clip / "gvhmr" / "overlay.ogv").read_bytes() == b"ogv of contents of overlay.mp4"
    assert result.files["selected.ogv"] == clip / "selected.ogv"
    meta = read_meta(clip)
    assert meta.selected_take == 2 and meta.status is ClipStatus.extracted
    assert any("running" in line for line in logs)
    assert not list(clip.glob(".*"))  # no scratch files left


def test_rerun_uses_selected_take_and_replaces_results(tmp_path: Path):
    clip = make_clip(tmp_path, [1, 2], selected=2)
    (clip / "gvhmr").mkdir()
    (clip / "gvhmr" / "stale.txt").write_text("old")
    result, _ = run(tmp_path, FakeWorker())
    assert result.take == 2
    assert sorted(p.name for p in (clip / "gvhmr").iterdir()) == [
        "hmr4d_results.pt",
        "overlay.mp4",
        "overlay.ogv",
    ]


def test_missing_ffmpeg_fails_before_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    clip = make_clip(tmp_path, [1])
    worker = FakeWorker()

    def no_ffmpeg():
        raise VideoError("ffmpeg not found; `brew install ffmpeg-full`")

    monkeypatch.setattr("anim8te.stages.extract.find_ffmpeg", no_ffmpeg)
    with pytest.raises(ExtractError, match="ffmpeg not found"):
        run(tmp_path, worker, ffmpeg=None)
    assert worker.uploads == [] and not (clip / "gvhmr").exists()


def test_failed_transcode_leaves_previous_results(tmp_path: Path):
    clip = make_clip(tmp_path, [1, 2], selected=1)
    run(tmp_path, FakeWorker())

    def broken(src: Path, dest: Path, ffmpeg: Path) -> None:
        raise VideoError(f"ffmpeg could not transcode {src.name}")

    with pytest.raises(ExtractError, match="could not transcode"):
        run(tmp_path, FakeWorker(), take=2, transcode=broken)
    assert (clip / "selected.mp4").read_bytes() == b"take 1"
    assert (clip / "selected.ogv").read_bytes() == b"ogv of take 1"
    assert read_meta(clip).selected_take == 1
    assert not list(clip.glob(".*"))


def test_failed_job_reports_error_and_leaves_clip_rerunnable(tmp_path: Path):
    clip = make_clip(tmp_path, [1])
    worker = FakeWorker(statuses=["running", "failed"], error="gvhmr exited with code 1")
    with pytest.raises(ExtractError, match="job job1 failed: gvhmr exited with code 1") as e:
        run(tmp_path, worker)
    assert "step 2" in str(e.value)  # log tail is shown
    meta = read_meta(clip)
    assert meta.status is ClipStatus.generated and meta.selected_take is None
    assert not (clip / "gvhmr").exists() and not (clip / "selected.mp4").exists()

    result, _ = run(tmp_path, FakeWorker())
    assert result.meta.status is ClipStatus.extracted


def test_failed_rerun_with_another_take_keeps_previous_results(tmp_path: Path):
    clip = make_clip(tmp_path, [1, 2])
    run(tmp_path, FakeWorker(), take=1)
    worker = FakeWorker()
    worker.fail_download = "overlay.mp4"
    with pytest.raises(ExtractError, match="404.*no file overlay.mp4"):
        run(tmp_path, worker, take=2)
    # gvhmr/ still matches the selected take
    meta = read_meta(clip)
    assert meta.selected_take == 1 and meta.status is ClipStatus.extracted
    assert (clip / "selected.mp4").read_bytes() == b"take 1"
    assert (clip / "gvhmr" / "overlay.mp4").exists()
    assert not (clip / ".gvhmr.part").exists()


def test_bad_token(tmp_path: Path):
    make_clip(tmp_path, [1])
    worker = FakeWorker()
    with pytest.raises(ExtractError, match="rejected the token"):
        run_extract(tmp_path, CLIP, worker.client(token="wrong"), sleep=lambda _: None)


def test_unreachable_worker(tmp_path: Path):
    make_clip(tmp_path, [1])

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = WorkerClient("http://worker", TOKEN, transport=httpx.MockTransport(refuse))
    with pytest.raises(ExtractError, match="unreachable at http://worker.*gvhmr-worker"):
        run_extract(tmp_path, CLIP, client)


def test_timeout(tmp_path: Path):
    make_clip(tmp_path, [1])
    ticks = iter(range(0, 10_000, 100))
    with pytest.raises(ExtractError, match="still running after 250 s"):
        run_extract(
            tmp_path,
            CLIP,
            FakeWorker(statuses=["running"]).client(),
            timeout_s=250,
            sleep=lambda _: None,
            clock=lambda: next(ticks),
        )


def test_unknown_clip(tmp_path: Path):
    with pytest.raises(ExtractError, match="no clip nope"):
        run_extract(tmp_path, "nope", FakeWorker().client())


def test_cli_unreachable_worker_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    make_clip(tmp_path, [1])
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("GVHMR_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("GVHMR_WORKER_URL", "http://127.0.0.1:9")  # discard port: refused
    monkeypatch.setattr("anim8te.stages.extract.find_ffmpeg", lambda: Path("/fake/ffmpeg"))
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "extract", CLIP])
    assert r.exit_code == 1
    assert "unreachable at http://127.0.0.1:9" in r.output
    assert json.loads((tmp_path / "clips" / CLIP / "meta.json").read_text())["status"] == (
        "generated"
    )


def test_cli_missing_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    make_clip(tmp_path, [1])
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GVHMR_WORKER_TOKEN", raising=False)
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "extract", CLIP])
    assert r.exit_code == 1 and "GVHMR_WORKER_TOKEN is not set" in r.output
