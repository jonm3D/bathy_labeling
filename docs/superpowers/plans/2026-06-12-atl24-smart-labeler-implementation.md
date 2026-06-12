# ATL24 Smart Labeler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lean local ATL24 photon labeler from the TransectView visualization ideas, with deterministic 10 km segments, sidecar labels, and a seeded smart-label proposal.

**Architecture:** Use a Python FastAPI backend for HDF5 scanning, segment inventory, label sidecars, reusable feature computation, and seeded proposals. Use a Vite/TypeScript frontend with Plotly for the editable profile view and MapLibre/deck.gl for local track context. Keep ATL24 class/confidence data out of normal labeler payloads and expose final labels as the primary display state.

**Tech Stack:** Python 3.10+, FastAPI, h5py, numpy, pytest; TypeScript, Vite, Plotly, MapLibre, deck.gl, node:test.

---

## File Structure

- Create `pyproject.toml`: package metadata, backend/runtime dependencies, pytest config, CLI entry point.
- Create `README.md`: local setup and run commands.
- Create `src/bathy_labeler/__init__.py`: package version.
- Create `src/bathy_labeler/cli.py`: Typer CLI for launching the server against an HDF5 folder and project folder.
- Create `src/bathy_labeler/backend/models.py`: dataclasses and constants for beams, labels, segments, and photon payloads.
- Create `src/bathy_labeler/backend/hdf5_store.py`: ATL24-like HDF5 discovery, beam metadata, segment generation, and segment photon reads.
- Create `src/bathy_labeler/backend/labels.py`: sidecar CSV/JSON read, validation, archive-before-replace, and status derivation.
- Create `src/bathy_labeler/backend/features.py`: reusable deterministic feature table used by proposals and later training/prediction.
- Create `src/bathy_labeler/backend/proposals.py`: deterministic seeded clustering proposal with residual `noise`.
- Create `src/bathy_labeler/backend/app.py`: FastAPI app exposing health, manifest, segments, segment payload, labels, proposal, and save endpoints.
- Create `tests/backend/test_hdf5_store.py`: synthetic HDF5 tests for scan, segments, row identity, beam strength, and day/night.
- Create `tests/backend/test_labels.py`: sidecar validation and archive tests.
- Create `tests/backend/test_features_proposals.py`: feature and seeded proposal behavior tests.
- Create `tests/backend/test_app.py`: API tests with FastAPI TestClient.
- Create `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.test.json`, `frontend/vite.config.ts`, `frontend/index.html`.
- Create `frontend/src/types.ts`: frontend API and label state types.
- Create `frontend/src/api.ts`: typed fetch wrappers.
- Create `frontend/src/labelState.ts`: manual/auto label editing state.
- Create `frontend/src/profilePlot.ts`: Plotly profile rendering, visual context window, editable segment shading, and selectable photon events.
- Create `frontend/src/mapView.ts`: simplified map/track context from TransectView ideas.
- Create `frontend/src/main.ts`: application orchestration.
- Create `frontend/src/styles.css`: quiet labeling-focused layout.
- Create `tests/frontend/labelState.test.ts`: state reducer tests.
- Create `tests/frontend/api.test.ts`: URL and request-shape tests.

## Task 1: Backend Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/bathy_labeler/__init__.py`
- Create: `src/bathy_labeler/backend/__init__.py`
- Create: `src/bathy_labeler/cli.py`

- [ ] **Step 1: Write the baseline import test**

Create `tests/backend/test_imports.py`:

```python
from bathy_labeler import __version__


def test_package_has_version():
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/backend/test_imports.py -q`

Expected: failure because `bathy_labeler` does not exist yet.

- [ ] **Step 3: Add project files**

Add package metadata, empty backend package, version, and a CLI that constructs the app from a source HDF5 folder and project folder.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/backend/test_imports.py -q`

Expected: `1 passed`.

## Task 2: Deterministic HDF5 Segment Inventory

**Files:**
- Create: `src/bathy_labeler/backend/models.py`
- Create: `src/bathy_labeler/backend/hdf5_store.py`
- Create: `tests/backend/test_hdf5_store.py`

- [ ] **Step 1: Write failing tests for inventory generation**

Tests create a synthetic ATL24-like HDF5 file with `gt1l`, `gt1r`, `lon_ph`, `lat_ph`, `x_atc`, `ortho_h`, `surface_h`, `index_ph`, `night_flag`, and `orbit_info/sc_orient`, then assert deterministic segment IDs, 10 km bounds, `source_row` mapping, day/night majority, and strong/weak beam derivation.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/backend/test_hdf5_store.py -q`

Expected: import or missing function failure.

- [ ] **Step 3: Implement models and HDF5 store**

Implement `Atl24Store.from_folder(source_root, project_root, segment_length_m=10000, context_margin_m=1000)`, recursive `.h5` discovery, required dataset validation, deterministic `segment_id`, segment payload reads, and transition-orientation rejection.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/backend/test_hdf5_store.py -q`

Expected: all inventory tests pass.

## Task 3: Sidecar Labels

**Files:**
- Create: `src/bathy_labeler/backend/labels.py`
- Create: `tests/backend/test_labels.py`

- [ ] **Step 1: Write failing tests for sidecar save/reload**

Tests assert that complete labels require one row per segment photon, include `source_row`, `index_ph`, `lat`, `lon`, `ortho_h_m`, `label`, and `label_source`, sort by `source_row`, write JSON metadata with row-key checksum, mark edited rows as `manual`, and archive older sidecars before replacement.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/backend/test_labels.py -q`

Expected: import or missing function failure.

- [ ] **Step 3: Implement sidecar manager**

Implement `LabelSidecarStore` with `load(segment)`, `save(segment, labels)`, `status_for(segment)`, legal-label validation, row-key checksum, current CSV/JSON paths, archive-before-replace, and stale detection.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/backend/test_labels.py -q`

Expected: all label tests pass.

## Task 4: Reusable Features and Seeded Proposal

**Files:**
- Create: `src/bathy_labeler/backend/features.py`
- Create: `src/bathy_labeler/backend/proposals.py`
- Create: `tests/backend/test_features_proposals.py`

- [ ] **Step 1: Write failing feature and proposal tests**

Tests assert feature output is keyed by `source_row` and `index_ph`, includes `night_flag`, `beam_strength`, `ortho_h_m`, `surface_h_m`, `dz_to_surface_m`, local density summaries, and histogram summaries. Proposal tests assert seeded classes are respected, unseeded semantic classes are not invented, seeded photons stay fixed, and unresolved photons become `noise`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/backend/test_features_proposals.py -q`

Expected: import or missing function failure.

- [ ] **Step 3: Implement feature generation**

Implement deterministic local feature generation using numpy, context photons for edge support, available-support normalization for density windows, and simple histogram mode summaries.

- [ ] **Step 4: Implement seeded proposal**

Implement a deterministic centroid classifier over scaled features with optional PCA disabled by default for v1, class centroids from manual seeds, fixed seeded labels, finite-feature filtering, distance-margin thresholding, and residual `noise`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/backend/test_features_proposals.py -q`

Expected: all feature/proposal tests pass.

## Task 5: FastAPI Endpoints

**Files:**
- Create: `src/bathy_labeler/backend/app.py`
- Create: `tests/backend/test_app.py`

- [ ] **Step 1: Write failing API tests**

Tests assert `/health`, `/manifest`, `/segments`, `/segments/{segment_id}`, `/segments/{segment_id}/labels`, `/segments/{segment_id}/proposal`, and `/segments/{segment_id}/labels` save behavior with JSON request payloads.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/backend/test_app.py -q`

Expected: import or missing endpoint failure.

- [ ] **Step 3: Implement app factory and endpoint models**

Implement `create_app(store, label_store, static_dir=None)`, static frontend mounting, JSON endpoint payloads, error handling for unknown segments, and label-source updates.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/backend/test_app.py -q`

Expected: all API tests pass.

## Task 6: Frontend State and API Tests

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.test.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/labelState.ts`
- Create: `tests/frontend/labelState.test.ts`
- Create: `tests/frontend/api.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Tests assert selected row assignment sets `label_source` to `manual`, proposal acceptance preserves manual edits, residual `noise` can be accepted as `auto`, and API URLs encode segment IDs safely.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test:frontend`

Expected: TypeScript or missing module failure.

- [ ] **Step 3: Implement frontend API and label reducer**

Implement typed fetch helpers and pure label-state helpers independent from the DOM.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test:frontend`

Expected: all frontend unit tests pass.

## Task 7: Frontend UI

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/src/profilePlot.ts`
- Create: `frontend/src/mapView.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Implement the labeler shell**

Build a first-screen application with segment sidebar, profile view, map context, class buttons, run-proposal button, save button, point size slider, and point opacity slider.

- [ ] **Step 2: Implement profile selection and rendering**

Use Plotly `scattergl` to render context photons and assigned segment photons, color by current final/proposal labels, show assigned segment bounds, and support click/lasso/box selection events.

- [ ] **Step 3: Implement simplified map context**

Use MapLibre/deck.gl to show segment track lines and selected segment context without ATL24 class filters.

- [ ] **Step 4: Build frontend**

Run: `cd frontend && npm run build`

Expected: `tsc` and `vite build` succeed.

## Task 8: End-to-End Verification

**Files:**
- Modify as needed based on failing tests.

- [ ] **Step 1: Run backend test suite**

Run: `PYTHONPATH=src pytest -q`

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend tests and build**

Run: `cd frontend && npm run test:frontend && npm run build`

Expected: all frontend tests pass and build succeeds.

- [ ] **Step 3: Smoke-test with reference example HDF5 data**

Run: `PYTHONPATH=src python -m bathy_labeler.cli /Users/jonathan/Documents/Research/icesat2-transectview/data/example/guam_subset --project /private/tmp/bathy-labeler-smoke --port 8787`

Expected: server starts, `/health` reports `ok`, and the frontend loads with segments.
