"""Stage 2: generate video takes from a performer's base image and a prompt (GDD §4 stage 2).

`plan_gen` turns a request into the final prompt, seeds and estimated cost without touching the
network; `run_gen` creates the clip, uploads the base image once and renders the takes
concurrently. Each finished take is written to `takes/<n>.mp4` first and to `meta.json` second,
so meta.json only ever lists takes whose file exists.
"""

from __future__ import annotations

import secrets
import threading
import time
import tomllib
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from anim8te.library import (
    ClipMeta,
    ClipStatus,
    RootMotionMode,
    Take,
    Template,
    clip_dir,
    new_clip_id,
    performers_dir,
    write_meta,
)

I2V_MODEL = "minimax/h3-max/image-to-video"
# fal pricing API, 2026-10-07: one unit price per second for every resolution.
PRICE_PER_S = {I2V_MODEL: 0.03}
RESOLUTIONS = ("480P", "768P", "1080P")
MIN_DURATION_S, MAX_DURATION_S = 0.92, 15.0


T = TypeVar("T")


class GenError(Exception):
    """A request that cannot run: unknown performer, bad duration, missing key."""


# --- templates -------------------------------------------------------------------------------


class PromptTemplate(BaseModel):
    """`anim8te/templates/<name>.toml`. The UI (M3.12) and agent assist (M3.18) read these too."""

    model_config = ConfigDict(extra="forbid")

    name: Template
    label: str
    description: str
    camera_rule: str
    treadmill_rule: str | None = None
    loop: bool = False
    root_motion: RootMotionMode = RootMotionMode.none
    tags: list[str] = Field(default_factory=list)

    def apply(self, prompt: str) -> str:
        """The prompt sent to fal: the user's text, the treadmill rule, then the camera rule."""
        parts = [_sentence(prompt)]
        if self.treadmill_rule and "treadmill" not in prompt.lower():
            parts.append(self.treadmill_rule)
        if not prompt.rstrip().endswith(self.camera_rule):
            parts.append(self.camera_rule)
        return " ".join(parts)


def _sentence(text: str) -> str:
    text = " ".join(text.split())
    return text if text.endswith((".", "!", "?")) else text + "."


def load_template(name: Template | str) -> PromptTemplate:
    name = Template(name)
    raw = resources.files("anim8te.templates").joinpath(f"{name.value}.toml").read_text()
    return PromptTemplate(name=name, **tomllib.loads(raw))


# --- planning --------------------------------------------------------------------------------


class GenRequest(BaseModel):
    performer: str
    prompt: str = Field(min_length=1)
    template: Template = Template.custom
    takes: int = Field(default=3, ge=1, le=8)
    duration: float = 5.0
    resolution: str = "768P"
    seed: int | None = None  # takes use seed, seed+1, ...; random seeds when None
    name: str | None = None
    model: str = I2V_MODEL


class GenPlan(BaseModel):
    """Everything `run_gen` will do, so `--dry-run` shows exactly what would be paid for."""

    request: GenRequest
    clip_id: str
    name: str
    base_image: Path
    final_prompt: str
    seeds: list[int]
    price_per_s: float
    template: PromptTemplate

    @property
    def cost_per_take_usd(self) -> float:
        return round(self.request.duration * self.price_per_s, 4)

    @property
    def estimated_cost_usd(self) -> float:
        return round(self.cost_per_take_usd * len(self.seeds), 4)

    def arguments(self, image_url: str, seed: int) -> dict:
        return {
            "image_url": image_url,
            "prompt": self.final_prompt,
            "duration": self.request.duration,
            "resolution": self.request.resolution,
            "seed": seed,
            "prompt_expansion_mode": "disabled",  # keep the prompt literal
        }


def plan_gen(library: Path, request: GenRequest) -> GenPlan:
    base = performers_dir(library) / request.performer / "base.png"
    if not base.is_file():
        raise GenError(f"performer {request.performer!r} has no base image at {base}")
    if not MIN_DURATION_S <= request.duration <= MAX_DURATION_S:
        raise GenError(f"duration must be {MIN_DURATION_S} to {MAX_DURATION_S} s")
    if request.resolution not in RESOLUTIONS:
        raise GenError(f"resolution must be one of {', '.join(RESOLUTIONS)}")
    if request.model not in PRICE_PER_S:
        raise GenError(f"no price known for {request.model!r}")

    template = load_template(request.template)
    if request.seed is None:
        seeds = [secrets.randbelow(2**31) for _ in range(request.takes)]
    else:
        seeds = [request.seed + i for i in range(request.takes)]
    name = request.name or " ".join(request.prompt.split()[:4])
    return GenPlan(
        request=request,
        clip_id=new_clip_id(name),
        name=name,
        base_image=base,
        final_prompt=template.apply(request.prompt),
        seeds=seeds,
        price_per_s=PRICE_PER_S[request.model],
        template=template,
    )


# --- running ---------------------------------------------------------------------------------


class VideoBackend(Protocol):
    """What stage 2 needs from fal. Tests pass a fake; `FalBackend` is the real one."""

    def upload(self, path: Path) -> str: ...
    def generate(self, model: str, arguments: dict) -> str: ...  # returns the video URL
    def download(self, url: str, dest: Path) -> None: ...


class FalBackend:
    def __init__(self, key: str, timeout_s: float = 900.0) -> None:
        import fal_client

        self._client = fal_client.SyncClient(key=key, default_timeout=timeout_s)

    def upload(self, path: Path) -> str:
        return self._client.upload_file(path)

    def generate(self, model: str, arguments: dict) -> str:
        return self._client.subscribe(model, arguments=arguments)["video"]["url"]

    def download(self, url: str, dest: Path) -> None:
        with urllib.request.urlopen(url, timeout=300) as r, dest.open("wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)


def is_retryable(exc: BaseException) -> bool:
    """Network trouble, timeouts, 408/429 and 5xx are worth retrying; other 4xx are not."""
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status in (408, 409, 429) or status >= 500
    if isinstance(exc, OSError | TimeoutError):
        return True
    # fal_client and httpx timeouts and transport errors, matched by name to keep imports lazy
    retryable = {"FalClientTimeoutError", "TransportError", "TimeoutException"}
    return any(cls.__name__ in retryable for cls in type(exc).__mro__)


def with_retries(
    fn: Callable[[], T],
    attempts: int,
    backoff_s: float,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == attempts or not is_retryable(exc):
                raise
            if on_retry:
                on_retry(attempt, exc)
            sleep(backoff_s * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


class TakeFailure(BaseModel):
    n: int
    seed: int
    error: str


class GenResult(BaseModel):
    clip: Path
    meta: ClipMeta
    failures: list[TakeFailure] = Field(default_factory=list)


def run_gen(
    library: Path,
    plan: GenPlan,
    backend: VideoBackend,
    *,
    attempts: int = 3,
    backoff_s: float = 5.0,
    max_workers: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = lambda _: None,
) -> GenResult:
    req = plan.request
    clip = clip_dir(library, plan.clip_id)
    takes_dir = clip / "takes"
    takes_dir.mkdir(parents=True, exist_ok=False)
    meta = ClipMeta(
        id=plan.clip_id,
        name=plan.name,
        tags=list(plan.template.tags),
        performer=req.performer,
        template=plan.template.name,
        prompt=req.prompt,
        final_prompt=plan.final_prompt,
        loop=plan.template.loop,
        root_motion=plan.template.root_motion,
    )
    write_meta(clip, meta)
    lock = threading.Lock()
    failures: list[TakeFailure] = []

    def retry_log(what: str) -> Callable[[int, BaseException], None]:
        return lambda attempt, exc: log(f"{what}: attempt {attempt} failed ({exc!r}), retrying")

    try:
        image_url = with_retries(
            lambda: backend.upload(plan.base_image),
            attempts,
            backoff_s,
            sleep,
            retry_log("upload"),
        )
    except Exception as exc:
        meta.status = ClipStatus.failed
        write_meta(clip, meta)
        failures = [TakeFailure(n=n, seed=s, error=f"upload: {exc!r}") for n, s in _numbered(plan)]
        return GenResult(clip=clip, meta=meta, failures=failures)

    def one(n: int, seed: int) -> None:
        args = plan.arguments(image_url, seed)
        dest = takes_dir / f"{n}.mp4"
        tmp = takes_dir / f".{n}.mp4.part"
        try:
            url = with_retries(
                lambda: backend.generate(req.model, args),
                attempts,
                backoff_s,
                sleep,
                retry_log(f"take {n}"),
            )
            with_retries(
                lambda: backend.download(url, tmp),
                attempts,
                backoff_s,
                sleep,
                retry_log(f"take {n} download"),
            )
            tmp.replace(dest)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            with lock:
                failures.append(TakeFailure(n=n, seed=seed, error=repr(exc)))
            log(f"take {n} (seed {seed}) failed: {exc!r}")
            return
        take = Take(
            n=n,
            seed=seed,
            model=req.model,
            duration_s=req.duration,
            resolution=req.resolution,
            cost_usd=plan.cost_per_take_usd,
            video_url=url,
        )
        with lock:
            meta.takes = sorted([*meta.takes, take], key=lambda t: t.n)
            write_meta(clip, meta)
        log(f"take {n} (seed {seed}) -> {dest}")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for future in [pool.submit(one, n, s) for n, s in _numbered(plan)]:
            future.result()

    meta.status = ClipStatus.generated if meta.takes else ClipStatus.failed
    write_meta(clip, meta)
    return GenResult(clip=clip, meta=meta, failures=sorted(failures, key=lambda f: f.n))


def _numbered(plan: GenPlan) -> list[tuple[int, int]]:
    return list(enumerate(plan.seeds, start=1))
