"""gvhmr-worker: video in, `hmr4d_results.pt` and an overlay video out (GDD §8).

The worker runs GVHMR's demo CLI as a subprocess, one job at a time, and never imports GVHMR, so
the CLI can be the Apple-Silicon fork (`gvhmr demo <video> -s`) or upstream on a CUDA box. The API
is kept small so a licensed or commercial service can replace it:

    POST /extract                     multipart `video`, `static_camera=true` -> job id
    GET  /jobs/{id}                   status, log tail, download URLs when done
    GET  /jobs/{id}/files/{name}      `hmr4d_results.pt` or `overlay.mp4`
    GET  /health                      unauthenticated liveness and install check

Every route except `/health` needs `Authorization: Bearer $GVHMR_WORKER_TOKEN`.
"""

import json
import os
import queue
import secrets
import shutil
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

JobStatus = Literal["queued", "running", "done", "failed"]
RESULT_FILES = ("hmr4d_results.pt", "overlay.mp4")
LOG_TAIL_LINES = 40

MOVING_CAMERA_REFUSED = (
    "static_camera=false is refused: this worker only runs still-camera takes (`gvhmr demo -s`). "
    "Moving-camera backends (VGGT, DUSt3R) ran the Mac out of memory in M0.10; send moving-camera "
    "takes to a CUDA worker, or reframe the shot so the camera stays still."
)


@dataclass(frozen=True)
class WorkerSettings:
    token: str
    gvhmr_bin: Path
    checkpoints: Path
    body_models: Path
    data_dir: Path
    timeout_s: float = 1800.0
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "WorkerSettings":
        env = dict(os.environ) if environ is None else environ
        token = env.get("GVHMR_WORKER_TOKEN", "")
        if not token:
            raise RuntimeError("GVHMR_WORKER_TOKEN is not set (environment or .env)")
        home = Path.home()
        checkpoints = Path(env.get("GVHMR_CHECKPOINTS", home / "motion-ai-checkpoints"))
        return cls(
            token=token,
            gvhmr_bin=Path(
                env.get("GVHMR_BIN", home / "motion-ai-tools" / "gvhmr" / ".venv" / "bin" / "gvhmr")
            ).expanduser(),
            checkpoints=checkpoints.expanduser(),
            body_models=Path(
                env.get("GVHMR_BODY_MODELS", checkpoints / "body_models")
            ).expanduser(),
            data_dir=Path(
                env.get("GVHMR_WORKER_DATA", home / ".cache" / "gvhmr-worker" / "jobs")
            ).expanduser(),
            timeout_s=float(env.get("GVHMR_WORKER_TIMEOUT", "1800")),
            host=env.get("GVHMR_WORKER_HOST", "127.0.0.1"),
            port=int(env.get("GVHMR_WORKER_PORT", "8765")),
        )


@dataclass
class Job:
    id: str
    dir: Path
    filename: str
    status: JobStatus = "queued"
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def log_path(self) -> Path:
        return self.dir / "gvhmr.log"

    def save(self) -> None:
        record = {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        (self.dir / "job.json").write_text(json.dumps(record, indent=2) + "\n")

    @classmethod
    def load(cls, job_dir: Path) -> "Job":
        record = json.loads((job_dir / "job.json").read_text())
        return cls(dir=job_dir, **record)


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    error: str | None = None
    log_tail: list[str] = []
    files: dict[str, str] = {}
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None


def log_tail(path: Path, lines: int = LOG_TAIL_LINES) -> list[str]:
    """Last lines of the GVHMR log. Progress bars redraw with `\\r`, so split on that too."""
    if not path.is_file():
        return []
    text = path.read_text(errors="replace")
    out = [ln.rstrip() for ln in text.replace("\r", "\n").split("\n")]
    return [ln for ln in out if ln.strip()][-lines:]


def find_overlay(out_dir: Path) -> Path | None:
    """The side-by-side in-cam and world render, else the in-cam render alone."""
    for pattern in ("*_3_incam_global_horiz.mp4", "1_incam.mp4"):
        found = sorted(out_dir.glob(pattern))
        if found:
            return found[0]
    return None


class JobRunner:
    """One GVHMR process at a time: MPS memory does not survive two in parallel."""

    def __init__(self, settings: WorkerSettings):
        self.settings = settings
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.thread: threading.Thread | None = None
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self._reload()

    def _reload(self) -> None:
        """Keep finished jobs across restarts; jobs that were mid-flight are marked failed."""
        for job_file in sorted(self.settings.data_dir.glob("*/job.json")):
            job = Job.load(job_file.parent)
            if job.status in ("queued", "running"):
                job.status, job.error = "failed", "worker restarted before the job finished"
                job.finished_at = time.time()
                job.save()
            self.jobs[job.id] = job

    def start(self) -> None:
        self.thread = threading.Thread(target=self._loop, name="gvhmr-runner", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.queue.put(None)
        if self.thread:
            self.thread.join(timeout=5)

    def submit(self, filename: str, upload) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.settings.data_dir / job_id
        job_dir.mkdir(parents=True)
        with (job_dir / "input.mp4").open("wb") as f:
            shutil.copyfileobj(upload, f)
        if (job_dir / "input.mp4").stat().st_size == 0:
            shutil.rmtree(job_dir)
            raise ValueError("video is empty")
        job = Job(id=job_id, dir=job_dir, filename=filename)
        job.save()
        with self.lock:
            self.jobs[job_id] = job
        self.queue.put(job_id)
        return job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def pending(self) -> int:
        with self.lock:
            return sum(j.status in ("queued", "running") for j in self.jobs.values())

    def _loop(self) -> None:
        while (job_id := self.queue.get()) is not None:
            job = self.get(job_id)
            if job is not None:
                self._run(job)

    def _set(self, job: Job, **changes) -> None:
        with self.lock:
            for key, value in changes.items():
                setattr(job, key, value)
            job.save()

    def _run(self, job: Job) -> None:
        s = self.settings
        self._set(job, status="running", started_at=time.time())
        out_root = job.dir / "out"
        cmd = [str(s.gvhmr_bin), "demo", str(job.dir / "input.mp4"), "-s", "-o", str(out_root)]
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env |= {"GVHMR_CHECKPOINTS": str(s.checkpoints), "GVHMR_BODY_MODELS": str(s.body_models)}
        error = None
        try:
            with job.log_path.open("w") as log:
                log.write("$ " + " ".join(cmd) + "\n")
                log.flush()
                proc = subprocess.run(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    cwd=job.dir,
                    timeout=s.timeout_s,
                )
            if proc.returncode != 0:
                error = f"gvhmr demo exited with code {proc.returncode}; see log_tail"
            else:
                error = self._collect(job, out_root / "input")
        except subprocess.TimeoutExpired:
            error = f"gvhmr demo timed out after {s.timeout_s:.0f} s"
        except OSError as exc:
            error = f"could not run {s.gvhmr_bin}: {exc}"
        self._set(job, status="failed" if error else "done", error=error, finished_at=time.time())

    @staticmethod
    def _collect(job: Job, out_dir: Path) -> str | None:
        results = out_dir / "hmr4d_results.pt"
        if not results.is_file():
            return f"gvhmr demo finished but wrote no {results.name}"
        overlay = find_overlay(out_dir)
        if overlay is None:
            return "gvhmr demo finished but wrote no overlay video"
        shutil.copy2(results, job.dir / "hmr4d_results.pt")
        shutil.copy2(overlay, job.dir / "overlay.mp4")
        return None


def create_app(settings: WorkerSettings) -> FastAPI:
    runner = JobRunner(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runner.start()
        yield
        runner.stop()

    app = FastAPI(title="gvhmr-worker", version="0.1.0", lifespan=lifespan)
    app.state.runner = runner
    bearer = HTTPBearer(auto_error=False)

    def authorize(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if creds is None or not secrets.compare_digest(
            creds.credentials.encode(), settings.token.encode()
        ):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "missing or wrong bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def job_or_404(job_id: str) -> Job:
        job = runner.get(job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job {job_id}")
        return job

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "gvhmr_bin": settings.gvhmr_bin.is_file(),
            "checkpoints": settings.checkpoints.is_dir(),
            "body_models": settings.body_models.is_dir(),
            # without ffprobe GVHMR silently assumes 30 fps and skips resampling 24 fps takes
            "ffprobe": shutil.which("ffprobe") is not None,
            "pending_jobs": runner.pending(),
        }

    @app.post("/extract", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(authorize)])
    def extract(
        video: Annotated[UploadFile, File(description="input video, .mp4")],
        static_camera: Annotated[bool, Form()] = True,
    ) -> dict:
        if not static_camera:
            raise HTTPException(422, MOVING_CAMERA_REFUSED)
        name = video.filename or "video.mp4"
        if not name.lower().endswith(".mp4"):
            raise HTTPException(422, "video must be an .mp4")
        try:
            job = runner.submit(name, video.file)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"job_id": job.id, "status": job.status}

    @app.get("/jobs/{job_id}", dependencies=[Depends(authorize)])
    def get_job(job_id: str, request: Request) -> JobView:
        job = job_or_404(job_id)
        files = {}
        if job.status == "done":
            files = {
                name: str(request.url_for("job_file", job_id=job.id, name=name))
                for name in RESULT_FILES
            }
        return JobView(
            job_id=job.id,
            status=job.status,
            error=job.error,
            log_tail=log_tail(job.log_path),
            files=files,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    @app.get("/jobs/{job_id}/files/{name}", name="job_file", dependencies=[Depends(authorize)])
    def job_file(job_id: str, name: str) -> FileResponse:
        job = job_or_404(job_id)
        if name not in RESULT_FILES:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no file {name}")
        if job.status != "done":
            raise HTTPException(status.HTTP_409_CONFLICT, f"job {job_id} is {job.status}")
        return FileResponse(job.dir / name, filename=name)

    return app


def main() -> None:
    """`gvhmr-worker`: read settings from the environment (and `./.env`) and serve."""
    import uvicorn

    load_dotenv()
    settings = WorkerSettings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
