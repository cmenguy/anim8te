"""Stage 4: extract 3D motion from the selected take through gvhmr-worker (GDD §4 stage 4).

`run_extract` uploads `takes/<n>.mp4` to the worker's `/extract` API, polls the job and
downloads `hmr4d_results.pt` and `overlay.mp4`. Only once both files are complete does it
replace `gvhmr/`, copy the take to `selected.mp4` and record `selected_take` and status
`extracted` in `meta.json`, so a failure at any point leaves the clip exactly as it was (its
`gvhmr/` always matches its `selected_take`) and the command can be re-run.
The worker API is documented in worker/README.md.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from pydantic import BaseModel

from anim8te.library import ClipMeta, ClipStatus, clip_dir, read_meta, write_meta

DEFAULT_WORKER_URL = "http://127.0.0.1:8765"
RESULT_FILES = ("hmr4d_results.pt", "overlay.mp4")


class ExtractError(Exception):
    """Anything that stops an extraction; the message is meant for the user as is."""


class ExtractResult(BaseModel):
    clip: Path
    meta: ClipMeta
    take: int
    job_id: str
    files: dict[str, Path]
    elapsed_s: float


def choose_take(meta: ClipMeta, take: int | None) -> int:
    """`--take n`, else the clip's selected take, else its only take."""
    numbers = [t.n for t in meta.takes]
    if not numbers:
        raise ExtractError(f"clip {meta.id} has no takes; run `anim8te gen` first")
    if take is not None:
        if take not in numbers:
            raise ExtractError(f"clip {meta.id} has no take {take} (takes: {_join(numbers)})")
        return take
    if meta.selected_take is not None:
        return meta.selected_take
    if len(numbers) == 1:
        return numbers[0]
    raise ExtractError(f"clip {meta.id} has {len(numbers)} takes; pick one with --take n")


def _join(numbers: list[int]) -> str:
    return ", ".join(map(str, numbers))


class WorkerClient:
    """The few gvhmr-worker calls stage 4 needs, with errors turned into ExtractError."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_s,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def submit(self, video: Path) -> str:
        with video.open("rb") as f:
            r = self._call(
                "POST",
                "/extract",
                files={"video": (video.name, f, "video/mp4")},
                data={"static_camera": "true"},
            )
        return r.json()["job_id"]

    def job(self, job_id: str) -> dict:
        return self._call("GET", f"/jobs/{job_id}").json()

    def download(self, job_id: str, name: str, dest: Path) -> None:
        try:
            with self._http.stream("GET", f"/jobs/{job_id}/files/{name}") as r:
                self._check(r)
                with dest.open("wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
        except httpx.TransportError as exc:
            raise self._unreachable(exc) from exc

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            r = self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise self._unreachable(exc) from exc
        self._check(r)
        return r

    def _unreachable(self, exc: httpx.TransportError) -> ExtractError:
        return ExtractError(
            f"gvhmr-worker is unreachable at {self.url} ({type(exc).__name__}). "
            "Start it with `uv run --project worker gvhmr-worker` or fix GVHMR_WORKER_URL."
        )

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.is_success:
            return
        if r.status_code == 401:
            raise ExtractError(
                "gvhmr-worker rejected the token (401): GVHMR_WORKER_TOKEN must match the "
                "value the worker was started with"
            )
        r.read()
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        path = r.request.url.path
        raise ExtractError(f"gvhmr-worker answered {r.status_code} to {path}: {detail}")


def run_extract(
    library: Path,
    clip_id: str,
    client: WorkerClient,
    *,
    take: int | None = None,
    poll_s: float = 2.0,
    timeout_s: float = 3600.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = lambda _: None,
) -> ExtractResult:
    clip = clip_dir(library, clip_id)
    if not (clip / "meta.json").is_file():
        raise ExtractError(f"no clip {clip_id} in {library}")
    meta = read_meta(clip)
    n = choose_take(meta, take)
    video = clip / "takes" / f"{n}.mp4"
    if not video.is_file():
        raise ExtractError(f"take {n} is listed in meta.json but {video} is missing")

    start = clock()
    job_id = client.submit(video)
    log(f"take {n}: job {job_id} submitted to {client.url}")

    last = None
    while True:
        job = client.job(job_id)
        status = job["status"]
        line = (job.get("log_tail") or [""])[-1].strip()
        progress = (status, line)
        if progress != last:
            elapsed = clock() - start
            log(f"[{elapsed:5.0f} s] {status}" + (f": {line}" if line else ""))
            last = progress
        if status == "done":
            break
        if status == "failed":
            tail = "\n".join("  " + s for s in (job.get("log_tail") or [])[-10:])
            raise ExtractError(
                f"job {job_id} failed: {job.get('error') or 'no error message'}"
                + (f"\nlast log lines:\n{tail}" if tail else "")
            )
        if clock() - start > timeout_s:
            raise ExtractError(
                f"job {job_id} still {status} after {timeout_s:.0f} s; "
                f"check {client.url}/jobs/{job_id} and re-run"
            )
        sleep(poll_s)

    scratch = clip / ".gvhmr.part"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir()
    try:
        for name in RESULT_FILES:
            client.download(job_id, name, scratch / name)
            log(f"downloaded {name} ({(scratch / name).stat().st_size / 1e6:.1f} MB)")
        # Results are complete: commit the take, its results and meta.json together.
        shutil.copyfile(video, scratch / ".selected.mp4")
        (scratch / ".selected.mp4").replace(clip / "selected.mp4")
        out = clip / "gvhmr"
        old = clip / ".gvhmr.old"
        shutil.rmtree(old, ignore_errors=True)
        if out.exists():
            out.replace(old)
        scratch.replace(out)
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    meta.selected_take = n
    meta.status = ClipStatus.extracted
    write_meta(clip, meta)
    return ExtractResult(
        clip=clip,
        meta=meta,
        take=n,
        job_id=job_id,
        files={name: out / name for name in RESULT_FILES},
        elapsed_s=clock() - start,
    )
