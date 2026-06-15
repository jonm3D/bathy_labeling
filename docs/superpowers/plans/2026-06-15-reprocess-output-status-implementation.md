# Reprocess Output Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add output-directory-aware progress status and revisit loading for per-beam ATL24 reprocess outputs.

**Architecture:** Keep H5/file status logic in `ReprocessSession`, because only the backend should understand expected manual output paths and HDF5 validation. The frontend receives source/beam status metadata, renders color-coded selector tiles, and refreshes status from save responses.

**Tech Stack:** Python/FastAPI/h5py/pytest backend, TypeScript/Plotly/Vite/node:test frontend.

---

### Task 1: Backend Status and Manual-Output Load Semantics

**Files:**
- Modify: `tests/backend/test_reprocess.py`
- Modify: `src/bathy_labeler/backend/reprocess.py`

- [ ] **Step 1: Write failing backend tests**

Add tests proving that source payloads report unclassified/partial/complete status, existing manual outputs initialize labels, missing outputs use original labels, mismatched manual files fail clearly, and save responses include refreshed status.

- [ ] **Step 2: Run backend tests and confirm failure**

Run: `env UV_CACHE_DIR=.uv-cache uv run --extra dev pytest tests/backend/test_reprocess.py -q`

Expected: FAIL because `status`, `beam_statuses`, `label_origin`, `manual_output_path`, and `source_status` are not implemented yet.

- [ ] **Step 3: Implement backend status helpers**

Add `BeamOutputStatus` and `FileOutputStatus` literal-compatible strings, derive expected output paths with `_output_path`, expose `source_status(source)`, and extend `ReprocessSource.to_dict(status=...)`.

- [ ] **Step 4: Implement manual-output label loading**

Change `read_beam()` to read photon geometry from the original H5, then initialize labels from the manual output H5 when present. Validate selected beam existence, `class_ph` existence, and row count equality before converting classes to label rows.

- [ ] **Step 5: Include refreshed status in saves**

After saving per-beam outputs, return `source_status` in `/reprocess/save` result.

- [ ] **Step 6: Verify backend tests pass**

Run: `env UV_CACHE_DIR=.uv-cache uv run --extra dev pytest tests/backend/test_reprocess.py -q`

Expected: PASS.

### Task 2: API Types and UI Status Helpers

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/reprocessStatus.ts`
- Create: `tests/frontend/reprocessStatus.test.ts`

- [ ] **Step 1: Write failing frontend helper tests**

Test status CSS class mapping and label-origin status text.

- [ ] **Step 2: Run frontend tests and confirm failure**

Run: `npm run test:frontend`

Expected: FAIL because `reprocessStatus.ts` does not exist and types do not expose status fields.

- [ ] **Step 3: Implement types and helpers**

Add `ReprocessBeamStatus`, `ReprocessFileStatus`, source status fields, beam payload `label_origin`/`manual_output_path`, save payload `source_status`, and helper functions for CSS class/status text.

- [ ] **Step 4: Verify frontend helper tests pass**

Run: `npm run test:frontend`

Expected: PASS.

### Task 3: UI Rendering and Save Refresh

**Files:**
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Wire status metadata into file and beam tiles**

Use status helpers in `reprocessFileButton()` and `reprocessBeamButton()`. File tiles show `complete`, `partial`, or `unclassified` plus `completed/total beams`; beam tiles show `complete` or `unclassified`.

- [ ] **Step 2: Show label origin when loading a beam**

Update active/status text after beam load to indicate whether labels came from manual output or original ATL24.

- [ ] **Step 3: Refresh selector status after save**

When save response includes `source_status`, replace the matching `ReprocessSource` entry in memory and rerender selectors so tile colors update immediately.

- [ ] **Step 4: Add status tile styles**

Add light green/yellow/red classes that cooperate with selected state and existing compact selector layout.

- [ ] **Step 5: Verify frontend tests and build**

Run: `npm run test:frontend` and `npm run build`.

Expected: PASS/build succeeds.

### Task 4: Full Verification, Server Restart, Commit, Push

**Files:**
- Modify as needed based on verification.

- [ ] **Step 1: Run full backend test suite**

Run: `env UV_CACHE_DIR=.uv-cache uv run --extra dev pytest tests/backend -q`

Expected: PASS.

- [ ] **Step 2: Run frontend verification**

Run: `npm run test:frontend` and `npm run build`.

Expected: PASS/build succeeds.

- [ ] **Step 3: Check diff hygiene**

Run: `git diff --check` and `git status --short`.

Expected: no whitespace errors; only intended files changed.

- [ ] **Step 4: Restart local server on port 8787**

Stop the old uvicorn session and start:

`env PYTHONPATH=src .venv/bin/python -m bathy_labeler.cli serve --input /Users/jonathan/Documents/Research/BASIN_Testing/icesat2/ATL24_002-Duck_Subset --output /Users/jonathan/Documents/Research/BASIN_Testing/icesat2/ATL24_v002_Duck_Relabeled --port 8787`

- [ ] **Step 5: Commit and push**

Commit message: `Add output status for reprocess workflow`

Push branch: `codex/default-mode`.
