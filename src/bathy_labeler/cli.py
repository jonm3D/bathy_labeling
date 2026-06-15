from __future__ import annotations

from pathlib import Path

try:
    import typer
except ModuleNotFoundError:  # pragma: no cover - exercised only without runtime deps installed
    typer = None


if typer is not None:
    app = typer.Typer(help="Run the ATL24 smart labeler.")

    @app.command()
    def serve(
        source: Path | None = typer.Argument(None, help="ATL24 folder. Required only with --training."),
        input_dir: Path | None = typer.Option(None, "--input", help="Default-mode ATL24 input folder."),
        output_dir: Path | None = typer.Option(None, "--output", help="Default-mode labeled output folder."),
        training: bool = typer.Option(False, "--training", help="Use 10 km sidecar training-label workflow."),
        project: Path | None = typer.Option(None, "--project", help="Project folder for training sidecars."),
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
            if source is None:
                raise typer.BadParameter("Training mode requires a source folder argument.")
            if project is None:
                raise typer.BadParameter("Training mode requires --project.")
            store = Atl24Store.from_folder(source_root=source, project_root=project)
            label_store = LabelSidecarStore(project_root=project)
            app_instance = create_app(store=store, label_store=label_store, static_dir=static_dir or default_static_dir())
        else:
            configured_input = input_dir or source
            session = ReprocessSession(input_dir=configured_input, output_dir=output_dir) if configured_input else ReprocessSession()
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
    return candidate if candidate.exists() else None


if __name__ == "__main__":
    main()
