from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bathy_labeler.backend.hdf5_store import Atl24Store
from bathy_labeler.backend.labels import LabelSidecarStore, LabelValidationError
from bathy_labeler.backend.proposals import generate_seeded_proposal
from bathy_labeler.backend.reprocess import ReprocessSession


def create_app(store: Atl24Store, label_store: LabelSidecarStore, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="ATL24 Smart Labeler", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, int | str]:
        return {"status": "ok", "segment_count": len(store.segments), "total_segment_photons": store.total_photons}

    @app.get("/manifest")
    def manifest() -> dict[str, Any]:
        return store.manifest()

    @app.get("/segments")
    def segments() -> dict[str, Any]:
        segment_rows = []
        for segment in store.segments:
            payload = store.read_segment(segment.segment_id)
            row = segment.to_dict()
            row["status"] = label_store.status_for(segment, payload.assigned)
            segment_rows.append(row)
        return {"count": len(segment_rows), "segments": segment_rows}

    @app.get("/segments/{segment_id}")
    def segment_payload(segment_id: str) -> dict[str, Any]:
        try:
            return store.read_segment(segment_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/segments/{segment_id}/labels")
    def segment_labels(segment_id: str) -> dict[str, Any]:
        if not _segment_exists(store, segment_id):
            raise HTTPException(status_code=404, detail=f"Unknown segment_id: {segment_id}")
        sidecar = label_store.load(segment_id)
        if sidecar is None:
            return {"status": "unlabeled", "rows": [], "metadata": {}}
        return {"status": sidecar.status, "rows": sidecar.rows, "metadata": sidecar.metadata}

    @app.post("/segments/{segment_id}/proposal")
    def segment_proposal(segment_id: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = store.read_segment(segment_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        result = generate_seeded_proposal(
            payload.assigned,
            payload.context,
            payload.segment.beam_strength,
            list(body.get("seeds", [])),
        )
        return {"rows": result.rows, "metadata": result.metadata}

    @app.put("/segments/{segment_id}/labels")
    def save_segment_labels(segment_id: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = store.read_segment(segment_id)
            sidecar = label_store.save(payload.segment, payload.assigned, list(body.get("labels", [])))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LabelValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": sidecar.status, "rows": sidecar.rows, "metadata": sidecar.metadata}

    if static_dir is not None:
        _mount_static_app(app, static_dir)

    return app


def create_reprocess_app(
    session: ReprocessSession,
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="ATL24 Reprocess Labeler", version="0.2.0")

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
            return session.configure(input_dir=body["input_dir"], output_dir=body.get("output_dir") or None)
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
            return session.reset_beam(source_relative_path=str(body["source"]), beam=str(body["beam"]))
        except KeyError as exc:
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


def _segment_exists(store: Atl24Store, segment_id: str) -> bool:
    return any(segment.segment_id == segment_id for segment in store.segments)


def _mount_static_app(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    assets = static_dir / "assets"
    if index.exists():
        @app.get("/")
        def index_file() -> FileResponse:
            return FileResponse(index)

    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
