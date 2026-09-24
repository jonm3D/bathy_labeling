from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Run the ATL24 bathymetry cleaner.")


@app.command(help="Run the local ATL24 bathymetry cleaner web app.")
def serve(
    input_dir: Path | None = typer.Option(None, "--input", help="ATL24 input folder."),
    output_dir: Path | None = typer.Option(
        None, "--output", help="Output folder for classified GeoPackages."
    ),
    review_config: Path | None = typer.Option(
        None,
        "--review-config",
        help="JSON config for SlideRule ATL03/ATL24 GeoParquet AOI annotation.",
    ),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
    static_dir: Path | None = typer.Option(
        None, "--static-dir", help="Built frontend directory."
    ),
) -> None:
    import uvicorn

    from bathy_labeler.backend.app import create_reprocess_app, create_review_app
    from bathy_labeler.backend.reprocess import ReprocessSession
    from bathy_labeler.backend.review import SlideRuleReviewSession

    static_dir = static_dir or default_static_dir()
    if review_config is not None:
        if input_dir is not None or output_dir is not None:
            raise typer.BadParameter(
                "--review-config cannot be combined with --input or --output."
            )
        app_instance = create_review_app(
            SlideRuleReviewSession(review_config), static_dir=static_dir
        )
    else:
        session = (
            ReprocessSession(input_dir=input_dir, output_dir=output_dir)
            if input_dir
            else ReprocessSession()
        )
        app_instance = create_reprocess_app(session, static_dir=static_dir)
    uvicorn.run(app_instance, host=host, port=port)


def default_static_dir() -> Path | None:
    candidate = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return candidate if (candidate / "index.html").exists() else None


if __name__ == "__main__":
    app()
