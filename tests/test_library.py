import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from anim8te.cli import app
from anim8te.library import (
    ClipMeta,
    ClipStatus,
    QCReport,
    QCStatus,
    RootMotionMode,
    Take,
    Template,
    list_clips,
    list_performers,
    new_clip_id,
    read_meta,
    read_qc,
    write_meta,
    write_qc,
)

FIXTURE = Path(__file__).parent / "fixtures" / "meta.json"


def test_meta_json_round_trips(tmp_path: Path):
    raw = json.loads(FIXTURE.read_text())
    meta = ClipMeta.model_validate(raw)
    assert meta.template is Template.locomotion
    assert meta.root_motion is RootMotionMode.synthesize
    assert meta.total_cost_usd == pytest.approx(0.30)

    # the model's JSON is the same document, field for field
    dumped = json.loads(meta.model_dump_json())
    assert dumped.keys() == raw.keys()
    assert ClipMeta.model_validate(dumped) == meta

    # and through the library's writer and reader
    clip = tmp_path / "clips" / meta.id
    write_meta(clip, meta, touch=False)
    assert read_meta(clip) == meta


def test_meta_rejects_inconsistent_documents():
    raw = json.loads(FIXTURE.read_text())
    for patch in (
        {"selected_take": 7},
        {"parent_clip": raw["id"]},
        {"status": "done-ish"},
        {"root_motion": "teleport"},
        {"segments": [{"name": "a", "start_s": 2.0, "end_s": 1.0}]},
        {"takes": raw["takes"] + [raw["takes"][0]]},
        {"unknown_field": 1},
    ):
        with pytest.raises(ValidationError):
            ClipMeta.model_validate({**raw, **patch})


def test_qc_placeholder(tmp_path: Path):
    assert read_qc(tmp_path).status is QCStatus.pending
    write_qc(tmp_path, QCReport(status=QCStatus.warn, metrics={"foot_skate_cm": 3.2}))
    assert read_qc(tmp_path).metrics == {"foot_skate_cm": 3.2}


def test_clip_ids_are_slugs_with_unique_suffix():
    ids = {new_clip_id("Parkour Vault!") for _ in range(50)}
    assert len(ids) == 50
    assert all(i.startswith("parkour-vault-") and len(i) == len("parkour-vault-") + 6 for i in ids)


def _library(tmp_path: Path) -> Path:
    lib = tmp_path / "library"
    (lib / "performers" / "perf01").mkdir(parents=True)
    (lib / "performers" / "perf01" / "base.png").write_bytes(b"png")
    (lib / "performers" / "perf02").mkdir()
    meta = ClipMeta(
        id="vault-abc123",
        name="vault",
        performer="perf01",
        template=Template.traversal,
        prompt="vault over a box",
        takes=[Take(n=1, seed=3, duration_s=5, resolution="768P", cost_usd=0.15)],
        status=ClipStatus.generated,
    )
    write_meta(lib / "clips" / meta.id, meta)
    (lib / "clips" / "old-m05" / "takes").mkdir(parents=True)  # pre-M1 clip, no meta.json
    (lib / "clips" / "broken").mkdir()
    (lib / "clips" / "broken" / "meta.json").write_text("{}")
    return lib


def test_list_clips_and_performers(tmp_path: Path):
    lib = _library(tmp_path)
    clips = {c.id: c for c in list_clips(lib)}
    assert clips["vault-abc123"].status == "generated"
    assert clips["old-m05"].status == "no meta.json"
    assert clips["broken"].status == "invalid meta.json"
    perfs = {p.id: p for p in list_performers(lib)}
    assert (perfs["perf01"].status, perfs["perf01"].clip_count) == ("ok", 1)
    assert perfs["perf02"].status == "missing base.png"


def test_lib_ls(tmp_path: Path):
    lib = _library(tmp_path)
    result = CliRunner().invoke(app, ["--library", str(lib), "lib", "ls"])
    assert result.exit_code == 0, result.output
    assert "clips (3)" in result.output
    assert "performers (2)" in result.output
    line = next(ln for ln in result.output.splitlines() if "vault-abc123" in ln)
    assert line.split() == ["vault-abc123", "generated", "perf01", "1", "pending", "vault"]


def test_lib_ls_empty_library(tmp_path: Path):
    result = CliRunner().invoke(app, ["--library", str(tmp_path), "lib", "ls"])
    assert result.exit_code == 0
    assert "clips (0)" in result.output
