"""`anim8te` command line. Thin wrappers: the work lives in `anim8te.stages`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from anim8te.config import Settings, load_settings
from anim8te.library import list_clips, list_performers

app = typer.Typer(help="Motion AI pipeline: gen, extract, clean, export.", no_args_is_help=True)
lib_app = typer.Typer(help="Inspect the clip library.", no_args_is_help=True)
app.add_typer(lib_app, name="lib")


def _settings(ctx: typer.Context) -> Settings:
    return ctx.obj


@app.callback()
def main(
    ctx: typer.Context,
    library: Annotated[
        Path | None,
        typer.Option(help="Library root. Defaults to ANIM8TE_LIBRARY, config.toml, or ./library."),
    ] = None,
) -> None:
    ctx.obj = load_settings(library=library)


def _not_yet(task: str) -> None:
    typer.echo(f"not implemented yet ({task})", err=True)
    raise typer.Exit(code=2)


@app.command()
def gen(ctx: typer.Context) -> None:
    """Generate video takes from a performer image and a prompt (stage 2)."""
    _not_yet("M1.3")


@app.command()
def extract(ctx: typer.Context) -> None:
    """Extract 3D motion from the selected take through gvhmr-worker (stage 4)."""
    _not_yet("M1.5")


@app.command()
def clean(ctx: typer.Context) -> None:
    """Clean the extracted motion: smoothing, ground alignment (stage 5)."""
    _not_yet("M1.9")


@app.command()
def export(ctx: typer.Context) -> None:
    """Write motion.glb on the canonical skeleton (stage 5)."""
    _not_yet("M1.10")


@lib_app.command("path")
def lib_path(ctx: typer.Context) -> None:
    """Print the resolved library root."""
    typer.echo(_settings(ctx).library)


@lib_app.command("ls")
def lib_ls(ctx: typer.Context) -> None:
    """List clips and performers with their status."""
    library = _settings(ctx).library
    clips = list_clips(library)
    performers = list_performers(library, clips)

    typer.echo(f"clips ({len(clips)})")
    rows = [("ID", "STATUS", "PERFORMER", "TAKES", "QC", "NAME")]
    for c in clips:
        m = c.meta
        rows.append(
            (
                c.id,
                c.status,
                m.performer if m else "-",
                str(len(m.takes)) if m else "-",
                c.qc.status.value if c.qc else "-",
                m.name if m else "-",
            )
        )
    _table(rows)

    typer.echo(f"\nperformers ({len(performers)})")
    rows = [("ID", "STATUS", "CLIPS")]
    rows += [(p.id, p.status, str(p.clip_count)) for p in performers]
    _table(rows)


def _table(rows: list[tuple[str, ...]]) -> None:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        typer.echo("  " + "  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)).rstrip())
