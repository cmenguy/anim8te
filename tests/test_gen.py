import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anim8te.cli import app
from anim8te.library import ClipStatus, RootMotionMode, Template, read_meta
from anim8te.stages.gen import (
    GenError,
    GenRequest,
    is_retryable,
    load_template,
    plan_gen,
    run_gen,
    with_retries,
)

CAMERA = "Static camera, full body visible."


@pytest.fixture
def library(tmp_path: Path) -> Path:
    perf = tmp_path / "performers" / "perf01"
    perf.mkdir(parents=True)
    (perf / "base.png").write_bytes(b"png")
    return tmp_path


class HTTPError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FakeBackend:
    """Records calls; `fail` maps a seed to the errors its next generate calls raise."""

    def __init__(self, fail: dict[int, list[Exception]] | None = None) -> None:
        self.fail = fail or {}
        self.uploads: list[Path] = []
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def upload(self, path: Path) -> str:
        self.uploads.append(path)
        return "https://fal.invalid/base.png"

    def generate(self, model: str, arguments: dict) -> str:
        with self.lock:
            self.calls.append(arguments)
            errors = self.fail.get(arguments["seed"])
            if errors:
                raise errors.pop(0)
        return f"https://fal.invalid/{arguments['seed']}.mp4"

    def download(self, url: str, dest: Path) -> None:
        dest.write_bytes(url.encode())


# --- templates -------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(Template))
def test_every_template_loads_and_ends_with_the_camera_rule(name: Template):
    t = load_template(name)
    assert t.name is name
    final = t.apply("The woman waves")
    assert final.startswith("The woman waves. ")
    assert final.endswith(CAMERA)


def test_locomotion_adds_treadmill_once():
    t = load_template("locomotion")
    assert t.loop and t.root_motion is RootMotionMode.synthesize
    final = t.apply("The woman jogs at an easy pace.")
    assert "treadmill" in final
    assert final.count("treadmill") == 1
    # the user already said it: no second treadmill sentence
    assert load_template("locomotion").apply("She jogs on a treadmill.").count("treadmill") == 1


def test_custom_and_traversal_have_no_treadmill():
    for name in ("custom", "traversal", "combat"):
        assert "treadmill" not in load_template(name).apply("She vaults the block.")


def test_camera_rule_is_not_doubled():
    t = load_template("custom")
    assert t.apply(f"She waves. {t.camera_rule}").count(CAMERA) == 1


# --- planning --------------------------------------------------------------------------------


def test_plan_with_seed_and_cost(library: Path):
    req = GenRequest(performer="perf01", prompt="She jogs", template="locomotion", seed=7)
    plan = plan_gen(library, req)
    assert plan.seeds == [7, 8, 9]
    assert plan.cost_per_take_usd == pytest.approx(0.15)
    assert plan.estimated_cost_usd == pytest.approx(0.45)
    assert plan.clip_id.startswith("she-jogs-")
    args = plan.arguments("u", 8)
    assert args["seed"] == 8 and args["prompt_expansion_mode"] == "disabled"


def test_plan_random_seeds_are_recorded(library: Path):
    plan = plan_gen(library, GenRequest(performer="perf01", prompt="x", takes=2))
    assert len(plan.seeds) == 2 and all(isinstance(s, int) for s in plan.seeds)


@pytest.mark.parametrize(
    "kwargs",
    [{"performer": "nobody"}, {"duration": 20}, {"duration": 0.5}, {"resolution": "4K"}],
)
def test_plan_rejects_bad_requests(library: Path, kwargs: dict):
    req = GenRequest(**{"performer": "perf01", "prompt": "x", **kwargs})
    with pytest.raises(GenError):
        plan_gen(library, req)


# --- running ---------------------------------------------------------------------------------


def _plan(library: Path, **kw):
    return plan_gen(library, GenRequest(performer="perf01", prompt="She jogs", seed=1, **kw))


def test_run_writes_takes_and_meta(library: Path):
    backend = FakeBackend()
    plan = _plan(library, template="locomotion")
    result = run_gen(library, plan, backend, sleep=lambda _: None)

    assert backend.uploads == [plan.base_image]  # uploaded once for all takes
    assert sorted(c["seed"] for c in backend.calls) == [1, 2, 3]
    for n in (1, 2, 3):
        assert (result.clip / "takes" / f"{n}.mp4").is_file()
    meta = read_meta(result.clip)
    assert meta == result.meta
    assert meta.status is ClipStatus.generated
    assert [(t.n, t.seed) for t in meta.takes] == [(1, 1), (2, 2), (3, 3)]
    assert meta.total_cost_usd == pytest.approx(0.45)
    assert meta.final_prompt == plan.final_prompt
    assert meta.template is Template.locomotion and meta.loop
    assert meta.tags == ["locomotion"]
    assert not list((result.clip / "takes").glob(".*"))  # no partial files left


def test_transient_errors_are_retried_with_backoff(library: Path):
    backend = FakeBackend(fail={2: [HTTPError(503), TimeoutError()]})
    sleeps: list[float] = []
    result = run_gen(library, _plan(library), backend, backoff_s=2, sleep=sleeps.append)
    assert not result.failures
    assert len(result.meta.takes) == 3
    assert sleeps == [2, 4]


def test_failed_take_leaves_meta_consistent(library: Path):
    # take 2 hits a 4xx (not retried), take 3 runs out of attempts
    backend = FakeBackend(fail={2: [HTTPError(422)], 3: [HTTPError(500)] * 3})
    result = run_gen(library, _plan(library), backend, attempts=3, sleep=lambda _: None)

    assert [f.n for f in result.failures] == [2, 3]
    assert [c["seed"] for c in backend.calls].count(2) == 1
    assert [c["seed"] for c in backend.calls].count(3) == 3
    meta = read_meta(result.clip)
    assert meta.status is ClipStatus.generated
    assert [t.n for t in meta.takes] == [1]
    assert sorted(p.name for p in (result.clip / "takes").iterdir()) == ["1.mp4"]


def test_all_takes_failing_marks_clip_failed(library: Path):
    backend = FakeBackend(fail={s: [HTTPError(400)] for s in (1, 2, 3)})
    result = run_gen(library, _plan(library), backend, sleep=lambda _: None)
    assert read_meta(result.clip).status is ClipStatus.failed
    assert read_meta(result.clip).takes == []


def test_upload_failure_marks_clip_failed(library: Path):
    class NoUpload(FakeBackend):
        def upload(self, path: Path) -> str:
            raise HTTPError(401)

    backend = NoUpload()
    result = run_gen(library, _plan(library), backend, sleep=lambda _: None)
    assert read_meta(result.clip).status is ClipStatus.failed
    assert backend.calls == [] and len(result.failures) == 3


def test_is_retryable():
    assert is_retryable(HTTPError(429)) and is_retryable(HTTPError(502))
    assert not is_retryable(HTTPError(404))
    assert is_retryable(ConnectionResetError())
    assert not is_retryable(ValueError())


def test_with_retries_gives_up_after_attempts():
    calls = []

    def boom():
        calls.append(1)
        raise TimeoutError

    with pytest.raises(TimeoutError):
        with_retries(boom, attempts=4, backoff_s=0, sleep=lambda _: None)
    assert len(calls) == 4


# --- CLI -------------------------------------------------------------------------------------


def test_cli_dry_run_prints_prompt_and_cost_and_creates_nothing(library: Path):
    args = ["--library", str(library), "gen", "--performer", "perf01", "--template"]
    args += ["locomotion", "--prompt", "She jogs", "--takes", "3", "--duration", "5"]
    args += ["--resolution", "768P", "--seed", "1", "--dry-run"]
    r = CliRunner().invoke(app, args)
    assert r.exit_code == 0, r.output
    assert "treadmill" in r.output and CAMERA in r.output
    assert "$0.45" in r.output
    assert not (library / "clips").exists()


def test_cli_unknown_performer_fails(library: Path):
    args = ["--library", str(library), "gen", "--performer", "x", "--prompt", "p", "--dry-run"]
    r = CliRunner().invoke(app, args)
    assert r.exit_code == 1
