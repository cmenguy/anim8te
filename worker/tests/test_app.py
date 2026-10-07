"""API tests against a fake `gvhmr` CLI that writes the files the real demo writes."""

from __future__ import annotations

import stat
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gvhmr_worker.app import MOVING_CAMERA_REFUSED, WorkerSettings, create_app

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

# Mirrors `gvhmr demo <video> -s -o <root>`: outputs land in <root>/<video stem>/.
FAKE_GVHMR = """#!{python}
import sys, pathlib
args = sys.argv[1:]
assert args[0] == "demo" and "-s" in args, args
video = pathlib.Path(args[1])
if video.read_bytes() == b"crash":
    print("Traceback: boom", file=sys.stderr)
    sys.exit(3)
out = pathlib.Path(args[args.index("-o") + 1]) / video.stem
out.mkdir(parents=True)
print("Recovered 4.1 s of motion\\r[####] 100%")
(out / "hmr4d_results.pt").write_bytes(b"results")
(out / "1_incam.mp4").write_bytes(b"incam")
(out / f"{{video.stem}}_3_incam_global_horiz.mp4").write_bytes(b"horiz")
"""


@pytest.fixture
def settings(tmp_path: Path) -> WorkerSettings:
    fake = tmp_path / "gvhmr"
    fake.write_text(FAKE_GVHMR.format(python=sys.executable))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "ckpt" / "body_models").mkdir(parents=True)
    return WorkerSettings(
        token=TOKEN,
        gvhmr_bin=fake,
        checkpoints=tmp_path / "ckpt",
        body_models=tmp_path / "ckpt" / "body_models",
        data_dir=tmp_path / "jobs",
        timeout_s=30,
    )


@pytest.fixture
def client(settings: WorkerSettings):
    with TestClient(create_app(settings)) as c:
        yield c


def submit(client: TestClient, body: bytes = b"mp4", **form) -> dict:
    r = client.post(
        "/extract",
        headers=AUTH,
        files={"video": ("take.mp4", body, "video/mp4")},
        data={"static_camera": "true", **form},
    )
    assert r.status_code == 202, r.text
    return r.json()


def wait(client: TestClient, job_id: str) -> dict:
    for _ in range(200):
        job = client.get(f"/jobs/{job_id}", headers=AUTH).json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish: {job}")


def test_health_needs_no_token(client):
    body = client.get("/health").json()
    assert body["ok"] and body["gvhmr_bin"] and body["checkpoints"]
    assert "ffprobe" in body


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_routes_need_the_token(client, headers):
    r = client.post("/extract", headers=headers, files={"video": ("a.mp4", b"x", "video/mp4")})
    assert r.status_code == 401
    assert client.get("/jobs/abc", headers=headers).status_code == 401


def test_extract_runs_to_done_and_serves_files(client):
    created = submit(client)
    assert created["status"] == "queued"
    job = wait(client, created["job_id"])
    assert job["status"] == "done", job
    assert job["error"] is None
    assert any("Recovered 4.1 s of motion" in ln for ln in job["log_tail"])
    assert set(job["files"]) == {"hmr4d_results.pt", "overlay.mp4"}
    assert client.get(job["files"]["hmr4d_results.pt"], headers=AUTH).content == b"results"
    # the side-by-side render wins over the in-cam one
    assert client.get(job["files"]["overlay.mp4"], headers=AUTH).content == b"horiz"


def test_failed_run_reports_exit_code_and_log(client):
    job = wait(client, submit(client, body=b"crash")["job_id"])
    assert job["status"] == "failed"
    assert "code 3" in job["error"]
    assert any("boom" in ln for ln in job["log_tail"])
    assert job["files"] == {}
    r = client.get(f"/jobs/{job['job_id']}/files/overlay.mp4", headers=AUTH)
    assert r.status_code == 409


def test_moving_camera_is_refused(client, settings):
    r = client.post(
        "/extract",
        headers=AUTH,
        files={"video": ("take.mp4", b"mp4", "video/mp4")},
        data={"static_camera": "false"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == MOVING_CAMERA_REFUSED
    assert not any(settings.data_dir.iterdir())


@pytest.mark.parametrize(("name", "body"), [("take.mov", b"x"), ("take.mp4", b"")])
def test_bad_upload_is_refused(client, name, body):
    r = client.post("/extract", headers=AUTH, files={"video": (name, body, "video/mp4")})
    assert r.status_code == 422


def test_unknown_job_and_file(client):
    assert client.get("/jobs/nope", headers=AUTH).status_code == 404
    job = wait(client, submit(client)["job_id"])
    assert client.get(f"/jobs/{job['job_id']}/files/input.mp4", headers=AUTH).status_code == 404


def test_restart_keeps_done_jobs_and_fails_interrupted_ones(settings):
    with TestClient(create_app(settings)) as c:
        done_id = wait(c, submit(c)["job_id"])["job_id"]
    # simulate a job that was running when the worker died
    stale = settings.data_dir / "stale"
    stale.mkdir()
    (stale / "job.json").write_text(
        '{"id": "stale", "filename": "t.mp4", "status": "running", "error": null,'
        ' "created_at": 0, "started_at": 0, "finished_at": null}'
    )
    with TestClient(create_app(settings)) as c:
        assert c.get(f"/jobs/{done_id}", headers=AUTH).json()["status"] == "done"
        stale_job = c.get("/jobs/stale", headers=AUTH).json()
        assert stale_job["status"] == "failed"
        assert "restarted" in stale_job["error"]


def test_settings_need_a_token():
    with pytest.raises(RuntimeError, match="GVHMR_WORKER_TOKEN"):
        WorkerSettings.from_env({})
    s = WorkerSettings.from_env({"GVHMR_WORKER_TOKEN": "t", "GVHMR_CHECKPOINTS": "/mnt/ckpt"})
    assert s.body_models == Path("/mnt/ckpt/body_models")
