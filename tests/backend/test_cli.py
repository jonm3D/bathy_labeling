from __future__ import annotations

from typer.testing import CliRunner

from bathy_labeler.cli import app


def test_default_cli_does_not_require_source_or_project() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--input" in result.stdout
    assert "--output" in result.stdout
    assert "--training" in result.stdout
    assert "--project" in result.stdout
