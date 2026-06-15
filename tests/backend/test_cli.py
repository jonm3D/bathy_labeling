from __future__ import annotations

from typer.testing import CliRunner

from bathy_labeler.cli import app
from bathy_labeler.cli import default_static_dir


def test_default_cli_focuses_on_atl24_cleanup() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ATL24 bathymetry cleaner" in result.stdout
    assert "--input" in result.stdout
    assert "--output" in result.stdout
    assert "--training" not in result.stdout
    assert "--training-source" not in result.stdout
    assert "--project" not in result.stdout
    assert "[SOURCE]" not in result.stdout


def test_default_static_dir_uses_built_frontend_from_checkout() -> None:
    candidate = default_static_dir()

    if candidate is not None:
        assert candidate.name == "dist"
        assert (candidate / "index.html").exists()
