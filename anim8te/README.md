# anim8te

Python package: `anim8te` CLI, pipeline stages under `stages/`, and the local daemon (GDD §4, §8). `cli.py` is a thin typer wrapper, `config.py` resolves settings, `library.py` holds the `meta.json`/`qc.json` models and the library layout, and stage code under `stages/` has no CLI or HTTP concerns.
