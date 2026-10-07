"""`anim8te` command line. Thin wrappers: the work lives in `anim8te.stages`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from anim8te.config import Settings, load_settings
from anim8te.library import Template, list_clips, list_performers
from anim8te.stages.gen import FalBackend, GenError, GenRequest, plan_gen, run_gen

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
def gen(
    ctx: typer.Context,
    performer: Annotated[str, typer.Option(help="Performer id under library/performers/.")],
    prompt: Annotated[str, typer.Option(help="One action, described plainly.")],
    template: Annotated[Template, typer.Option(help="Adds camera and treadmill rules.")] = (
        Template.custom
    ),
    takes: Annotated[int, typer.Option(min=1, max=8, help="Takes to generate.")] = 3,
    duration: Annotated[float, typer.Option(help="Seconds per take (0.92 to 15).")] = 5.0,
    resolution: Annotated[str, typer.Option(help="480P, 768P or 1080P.")] = "768P",
    seed: Annotated[int | None, typer.Option(help="Seed of take 1; take n uses seed+n-1.")] = None,
    name: Annotated[str | None, typer.Option(help="Clip name; defaults to the prompt.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the final prompt and cost; call nothing.")
    ] = False,
) -> None:
    """Generate video takes from a performer image and a prompt (stage 2)."""
    settings = _settings(ctx)
    request = GenRequest(
        performer=performer,
        prompt=prompt,
        template=template,
        takes=takes,
        duration=duration,
        resolution=resolution,
        seed=seed,
        name=name,
    )
    try:
        plan = plan_gen(settings.library, request)
    except GenError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"clip:      {plan.clip_id}{' (not created)' if dry_run else ''}")
    typer.echo(f"model:     {request.model}, {duration:g} s, {resolution}")
    typer.echo(f"image:     {plan.base_image}")
    typer.echo(f"seeds:     {', '.join(map(str, plan.seeds))}")
    typer.echo(f"prompt:    {plan.final_prompt}")
    typer.echo(
        f"estimated: ${plan.estimated_cost_usd:.2f} "
        f"({len(plan.seeds)} x ${plan.cost_per_take_usd:.2f} at ${plan.price_per_s}/s)"
    )
    if dry_run:
        return
    if settings.fal_key is None:
        typer.echo("error: FAL_KEY is not set (https://fal.ai/dashboard/keys)", err=True)
        raise typer.Exit(code=1)

    backend = FalBackend(settings.fal_key.get_secret_value())
    result = run_gen(settings.library, plan, backend, log=lambda m: typer.echo(m, err=True))
    m = result.meta
    typer.echo(f"status:    {m.status.value}, {len(m.takes)}/{len(plan.seeds)} takes")
    typer.echo(f"cost:      ${m.total_cost_usd:.2f}")
    typer.echo(f"meta:      {result.clip / 'meta.json'}")
    for f in result.failures:
        typer.echo(f"failed:    take {f.n} (seed {f.seed}): {f.error}", err=True)
    if result.failures:
        raise typer.Exit(code=1)


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
