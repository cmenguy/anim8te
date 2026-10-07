from pathlib import Path

from typer.testing import CliRunner

from motionai.cli import app
from motionai.config import load_settings


def test_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("gen", "extract", "clean", "export", "lib"):
        assert name in result.output


def test_settings_precedence(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("FAL_KEY=from-dotenv\nMOTIONAI_LIBRARY=/dotenv/lib\n")
    config = tmp_path / "config.toml"
    config.write_text(
        'library = "/toml/lib"\ngvhmr_worker_url = "http://toml:8000"\nfal_key = "ignored"\n'
    )

    s = load_settings(env_file=env_file, config_file=config, environ={})
    assert s.library == Path("/dotenv/lib")
    assert s.gvhmr_worker_url == "http://toml:8000"
    assert s.fal_key.get_secret_value() == "from-dotenv"

    s = load_settings(env_file=tmp_path / "missing", config_file=config, environ={})
    assert s.library == Path("/toml/lib")
    assert s.fal_key is None  # secrets never come from config.toml

    s = load_settings(
        library=tmp_path / "cli",
        env_file=env_file,
        config_file=config,
        environ={"MOTIONAI_LIBRARY": "/environ/lib"},
    )
    assert s.library == (tmp_path / "cli").resolve()


def test_cli_library_option(tmp_path: Path):
    result = CliRunner().invoke(app, ["--library", str(tmp_path), "lib", "path"])
    assert result.exit_code == 0
    assert result.output.strip() == str(tmp_path.resolve())
