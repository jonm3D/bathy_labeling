from __future__ import annotations

from pathlib import Path

try:
    import typer
except ModuleNotFoundError:  # pragma: no cover - exercised only without runtime deps installed
    typer = None


if typer is not None:
    app = typer.Typer(help="Run the ATL24 bathymetry cleaner.")

    @app.command(help="Run the local ATL24 bathymetry cleaner web app.")
    def serve(
        input_dir: Path | None = typer.Option(None, "--input", help="ATL24 input folder."),
        output_dir: Path | None = typer.Option(None, "--output", help="Cleaned ATL24 output folder."),
        training_source: Path | None = typer.Option(None, "--training-source", hidden=True),
        training: bool = typer.Option(
            False,
            "--training",
            help="Use the experimental 10 km sidecar training-label workflow.",
            hidden=True,
        ),
        project: Path | None = typer.Option(
            None,
            "--project",
            help="Project folder for experimental training sidecars.",
            hidden=True,
        ),
        host: str = typer.Option("127.0.0.1", "--host"),
        port: int = typer.Option(8787, "--port"),
        static_dir: Path | None = typer.Option(None, "--static-dir", help="Built frontend directory."),
    ) -> None:
        import uvicorn

        from bathy_labeler.backend.app import create_app, create_reprocess_app
        from bathy_labeler.backend.hdf5_store import Atl24Store
        from bathy_labeler.backend.labels import LabelSidecarStore
        from bathy_labeler.backend.reprocess import ReprocessSession

        if training:
            if training_source is None:
                raise typer.BadParameter("Training mode requires --training-source.")
            if project is None:
                raise typer.BadParameter("Training mode requires --project.")
            store = Atl24Store.from_folder(source_root=training_source, project_root=project)
            label_store = LabelSidecarStore(project_root=project)
            app_instance = create_app(store=store, label_store=label_store, static_dir=static_dir or default_static_dir())
        else:
            session = ReprocessSession(input_dir=input_dir, output_dir=output_dir) if input_dir else ReprocessSession()
            app_instance = create_reprocess_app(session=session, static_dir=static_dir or default_static_dir())
        uvicorn.run(
            app_instance,
            host=host,
            port=port,
        )
else:
    app = None


def main() -> None:
    if app is None:
        raise RuntimeError("The CLI requires typer. Install bathy-labeler with runtime dependencies.")
    app()


def default_static_dir() -> Path | None:
    candidate = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return candidate if (candidate / "index.html").exists() else None


if __name__ == "__main__":
    main()
