from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bathy_labeler.backend.reprocess import ReprocessSession
from bathy_labeler.backend.review import SlideRuleReviewSession


def create_reprocess_app(
    session: ReprocessSession,
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="ATL24 Bathymetry Cleaner", version="0.2.0")

    @app.get("/health")
    def health() -> dict[str, object]:
        manifest = session.manifest()
        return {"status": "ok", **manifest}

    @app.get("/manifest")
    def manifest() -> dict[str, object]:
        return session.manifest()

    @app.post("/reprocess/session")
    def configure_session(body: dict[str, Any]) -> dict[str, object]:
        try:
            return session.configure(
                input_dir=body["input_dir"],
                output_dir=body.get("output_dir") or None,
            )
        except (FileNotFoundError, NotADirectoryError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/reprocess/sources")
    def reprocess_sources() -> dict[str, object]:
        try:
            return session.sources_payload()
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/reprocess/beam")
    def reprocess_beam(source: str, beam: str) -> dict[str, object]:
        try:
            return session.read_beam(source, beam)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/reprocess/proposal")
    def reprocess_proposal(body: dict[str, Any]) -> dict[str, object]:
        try:
            return session.propose(
                source_relative_path=str(body["source"]),
                beam=str(body["beam"]),
                seeds=list(body.get("seeds", [])),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/reprocess/reset")
    def reprocess_reset(body: dict[str, Any]) -> dict[str, object]:
        try:
            return session.reset_beam(
                source_relative_path=str(body["source"]), beam=str(body["beam"])
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/reprocess/dem-sample")
    def reprocess_dem_sample(body: dict[str, Any]) -> dict[str, object]:
        try:
            return session.sample_dem(
                source_relative_path=str(body["source"]),
                beam=str(body["beam"]),
                dem_path=str(body["dem_path"]),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/reprocess/save")
    def reprocess_save(body: dict[str, Any]) -> dict[str, object]:
        try:
            return session.save_source(
                source_relative_path=str(body["source"]),
                beam_labels=dict(body.get("beam_labels", {})),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if static_dir is not None:
        _mount_static_app(app, static_dir)

    return app


def create_review_app(
    session: SlideRuleReviewSession,
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="ATL24 AOI Labeler", version="0.3.0")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", **session.manifest()}

    @app.get("/manifest")
    def manifest() -> dict[str, object]:
        return session.manifest()

    @app.get("/review/sources")
    def review_sources() -> dict[str, object]:
        return session.sources_payload()

    @app.get("/review/track")
    def review_track(source: str, track: str) -> dict[str, object]:
        try:
            return session.read_track(source, track)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/review/track/labels")
    def save_review_track(body: dict[str, Any]) -> dict[str, object]:
        try:
            return session.save_track(
                source_id=str(body["source"]),
                track_key=str(body["track"]),
                labels=list(body.get("labels", [])),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if static_dir is not None:
        _mount_static_app(app, static_dir)

    return app


def _mount_static_app(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    assets = static_dir / "assets"
    if index.exists():

        @app.get("/")
        def index_file() -> FileResponse:
            return FileResponse(index)

    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
