"""`anim8te` command line. Thin wrappers: the work lives in `anim8te.stages`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from anim8te.config import Settings, load_settings

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
