"""Configuration: environment, then `.env`, then `~/.config/anim8te/config.toml`, then defaults.

Secrets (`FAL_KEY`, `GVHMR_WORKER_TOKEN`, `ANTHROPIC_API_KEY`) are read from the environment or
`.env` only, never from the TOML file, so the config file can be shared without leaking them.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, SecretStr

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "anim8te" / "config.toml"

# setting name -> environment variable
_ENV_NAMES = {
    "library": "ANIM8TE_LIBRARY",
    "gvhmr_worker_url": "GVHMR_WORKER_URL",
    "fal_key": "FAL_KEY",
    "gvhmr_worker_token": "GVHMR_WORKER_TOKEN",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}
_SECRETS = {"fal_key", "gvhmr_worker_token", "anthropic_api_key"}


class Settings(BaseModel):
    library: Path
    gvhmr_worker_url: str | None = None
    fal_key: SecretStr | None = None
    gvhmr_worker_token: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None


def load_settings(
    library: Path | None = None,
    env_file: Path | None = None,
    config_file: Path | None = None,
    environ: dict[str, str] | None = None,
) -> Settings:
    """Resolve settings. `library` (the CLI's `--library`) wins over every other source."""
    environ = dict(os.environ) if environ is None else environ
    env_file = Path(".env") if env_file is None else env_file
    config_file = DEFAULT_CONFIG_PATH if config_file is None else config_file

    dotenv = {k: v for k, v in dotenv_values(env_file).items() if v} if env_file.is_file() else {}
    toml: dict = {}
    if config_file.is_file():
        with config_file.open("rb") as f:
            toml = tomllib.load(f)

    values: dict[str, object] = {}
    for name, env_name in _ENV_NAMES.items():
        if environ.get(env_name):
            values[name] = environ[env_name]
        elif env_name in dotenv:
            values[name] = dotenv[env_name]
        elif name not in _SECRETS and name in toml:
            values[name] = toml[name]

    if library is not None:
        values["library"] = library
    values.setdefault("library", Path("library"))
    values["library"] = Path(values["library"]).expanduser().resolve()
    return Settings(**values)
