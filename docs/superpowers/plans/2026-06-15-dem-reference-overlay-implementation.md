# DEM Reference Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users provide a local GeoTIFF DEM path, sample it along the selected ATL24 beam, and show it as a toggleable reference trace in the transect plot.

**Architecture:** Add a backend DEM sampler that lazily opens a raster with rasterio, transforms ATL24 lon/lat points into raster CRS, and samples only requested track coordinates. Expose it through a reprocess endpoint and render the returned along-track values as an optional Plotly line+marker trace; this data never feeds labels, smart labeling, or save output.

**Tech Stack:** FastAPI, h5py, numpy, rasterio, pyproj, Plotly, TypeScript.

---

### Task 1: Backend DEM Sampler

**Files:**
- Create: `src/bathy_labeler/backend/dem.py`
- Modify: `pyproject.toml`
- Test: `tests/backend/test_dem.py`

- [ ] **Step 1: Write failing tests**

Create tests that write a small GeoTIFF in EPSG:32655, transform known lon/lat ATL24-style points into that CRS, and assert `sample_dem_along_track()` returns `x_atc_m`, sampled heights, `None` for out-of-bounds/nodata, and metadata. Use `pytest.importorskip("rasterio")` and `pytest.importorskip("pyproj")` at the top so tests are explicit about raster dependencies.

- [ ] **Step 2: Verify tests fail**

Run: `env UV_CACHE_DIR=.uv-cache uv run --extra dev pytest tests/backend/test_dem.py -q`
Expected before implementation: import or missing function failure.

- [ ] **Step 3: Implement sampler**

Implement `sample_dem_along_track(dem_path: Path, lon: list[float], lat: list[float], x_atc_m: list[float]) -> dict[str, object]`.
Use `rasterio.open()` and `rasterio.vrt.WarpedVRT` with `crs="EPSG:4326"` only when needed, then call `dataset.sample(zip(lon, lat), masked=True)`. This keeps reads spatially aware and compatible with large tiled rasters/COGs. Convert masked/nodata/nonfinite samples to `None`.

- [ ] **Step 4: Verify tests pass**

Run: `env UV_CACHE_DIR=.uv-cache uv run --extra dev pytest tests/backend/test_dem.py -q`
Expected: pass.

### Task 2: Reprocess DEM Endpoint

**Files:**
- Modify: `src/bathy_labeler/backend/reprocess.py`
- Modify: `src/bathy_labeler/backend/app.py`
- Test: `tests/backend/test_reprocess_app.py`

- [ ] **Step 1: Write failing endpoint test**

Extend the reprocess app test with a temporary GeoTIFF and POST `/reprocess/dem-sample` using `{source, beam, dem_path}`. Assert the response includes the source, beam, DEM metadata, and a sample count matching the beam photon count.

- [ ] **Step 2: Verify test fails**

Run: `env UV_CACHE_DIR=.uv-cache uv run --extra dev pytest tests/backend/test_reprocess_app.py -q`
Expected before endpoint implementation: 404 or missing endpoint.

- [ ] **Step 3: Implement endpoint**

Add `ReprocessSession.sample_dem(source_relative_path, beam, dem_path)` that reads the selected beam photons and calls `sample_dem_along_track()`. Add FastAPI route `POST /reprocess/dem-sample`.

- [ ] **Step 4: Verify test passes**

Run: `env UV_CACHE_DIR=.uv-cache uv run --extra dev pytest tests/backend/test_reprocess_app.py -q`
Expected: pass.

### Task 3: Frontend DEM Trace

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/profilePlot.ts`
- Test: `tests/frontend/profileRevision.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Add a revision test asserting the profile data revision changes when DEM visibility or DEM sample values change. Add type-level coverage for the new `DemSamplePayload` shape by importing it into the test.

- [ ] **Step 2: Verify tests fail**

Run: `npm run test:frontend` from `frontend/`.
Expected before implementation: missing type/settings errors.

- [ ] **Step 3: Implement UI and plotting**

Add a `DEM GeoTIFF` path text input and `Show DEM` toggle. Store the current DEM payload in memory. When beam, path, or toggle changes, fetch `/reprocess/dem-sample`; render a Plotly `scattergl` trace with `mode: "lines+markers"`, thin dark line, and small dot markers. DEM data does not affect labels, selected rows, proposals, or saves.

- [ ] **Step 4: Verify frontend tests pass**

Run: `npm run test:frontend` from `frontend/`.
Expected: pass.

### Task 4: Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the DEM overlay**

Add a short README note that the DEM path is sampled as a reference-only overlay and is not saved into labels or output H5 files.

- [ ] **Step 2: Run full checks**

Run:

```bash
env UV_CACHE_DIR=.uv-cache uv run --extra dev pytest tests/backend -q
npm run test:frontend
npm run build
```

Expected: backend and frontend tests pass; Vite may keep the existing Plotly bundle warning.
