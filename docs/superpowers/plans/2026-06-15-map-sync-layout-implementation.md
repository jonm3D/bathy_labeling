# Map Sync and Labeler Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stack labeler controls and file/beam navigation on the left, stack map/profile views on the right, and add bidirectional map/profile along-track sync.

**Architecture:** Keep the sync math in a pure `mapSync.ts` module, expose small sync hooks from `profilePlot.ts` and `mapView.ts`, and let `main.ts` coordinate toggle state and loop guards. Keep the layout change in `index.html` and `styles.css` without changing labeling data flow.

**Tech Stack:** TypeScript, Vite, Plotly, MapLibre GL, node:test.

---

## File Structure

- Create `frontend/src/mapSync.ts`: pure range, interpolation, bearing, relayout extraction, and screen-clipping helpers.
- Create `tests/frontend/mapSync.test.ts`: unit coverage for sync geometry and relayout parsing.
- Modify `frontend/src/profilePlot.ts`: export x-range setter and relayout handler support.
- Modify `frontend/src/mapView.ts`: add camera sync, visible-range extraction, camera save/restore, and moveend subscriptions.
- Modify `frontend/src/main.ts`: wire `Sync with Map` state, profile/map callbacks, and payload lifecycle updates.
- Modify `frontend/index.html`: move the picker below controls and move map/profile into the right workspace column.
- Modify `frontend/src/styles.css`: implement the two-column/two-row layout and style the sync toggle.

## Task 1: Pure Map Sync Helpers

**Files:**
- Create: `frontend/src/mapSync.ts`
- Create: `tests/frontend/mapSync.test.ts`

- [ ] **Step 1: Write failing tests**

Add tests that create a minimal `SegmentPayload` with `x_atc_m`, `lon`, and `lat`, then assert:

```ts
assert.deepEqual(getSegmentDistanceRange(samplePayload()), [0, 20]);
assert.deepEqual(extractPlotlyXRange({ "xaxis.range[0]": 3, "xaxis.range[1]": 8 }, [0, 20]), [3, 8]);
assert.deepEqual(extractPlotlyXRange({ "xaxis.autorange": true }, [0, 20]), [0, 20]);
const view = computeMapSyncView(samplePayload(), [15, 5]);
assert.deepEqual(view?.rangeKm, [5, 15]);
assert.equal(computeMapSyncView(singlePointPayload(), [0, 1]), null);
```

Also test `computeVisibleDistanceRangeFromScreen` with a segment crossing the viewport and with a viewport extending beyond the endpoints.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test:frontend`

Expected: TypeScript fails because `frontend/src/mapSync.ts` does not exist.

- [ ] **Step 3: Implement helper module**

Implement:

```ts
export type DistanceRange = [number, number];
export type LngLatTuple = [number, number];
export interface MapSyncView { rangeKm: DistanceRange; start: LngLatTuple; end: LngLatTuple; center: LngLatTuple; bearing: number; }
export interface ScreenSample { distanceKm: number; x: number; y: number; }
export interface ScreenViewport { left: number; top: number; right: number; bottom: number; }
export function getSegmentDistanceRange(payload: SegmentPayload): DistanceRange | null;
export function computeMapSyncView(payload: SegmentPayload, requestedRange: DistanceRange | null): MapSyncView | null;
export function extractPlotlyXRange(update: Record<string, unknown>, fallbackRange: DistanceRange | null): DistanceRange | null;
export function computeVisibleDistanceRangeFromScreen(samples: ScreenSample[], viewport: ScreenViewport): DistanceRange | null;
```

Use the reference app's interpolation, Mercator bearing, numeric range parsing, and viewport clipping logic, adapted from `distance_km` to `context.x_atc_m / 1000`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test:frontend`

Expected: all frontend tests pass.

## Task 2: Profile Plot Range Hooks

**Files:**
- Modify: `frontend/src/profilePlot.ts`

- [ ] **Step 1: Add failing compile usage**

Update `main.ts` imports to expect these profile APIs:

```ts
import { clearProfile, renderProfile, setProfileXRange, type ProfileRelayoutHandler, type ProfileSettings } from "./profilePlot.js";
```

Run: `cd frontend && npm run test:frontend`

Expected: TypeScript fails because `setProfileXRange` and `ProfileRelayoutHandler` are not exported.

- [ ] **Step 2: Implement profile exports**

Add:

```ts
export type ProfileRelayoutHandler = (update: Record<string, unknown>) => void;
export async function setProfileXRange(container: HTMLElement, range: [number, number]): Promise<void> {
  await Plotly.relayout(container, { "xaxis.range": range });
}
```

Extend `renderProfile` with an optional `onRelayout?: ProfileRelayoutHandler` parameter and attach both `plotly_relayout` and `plotly_relayouting` after rendering. Keep existing selection listeners intact.

- [ ] **Step 3: Run tests**

Run: `cd frontend && npm run test:frontend`

Expected: all frontend tests pass or the next compile error points to map/main APIs not yet implemented.

## Task 3: Map View Sync Surface

**Files:**
- Modify: `frontend/src/mapView.ts`

- [ ] **Step 1: Add failing compile usage**

Update `main.ts` to expect map APIs:

```ts
mapView.syncToSegmentRange(syncView, animated);
mapView.getVisibleSegmentRange(currentPayload);
mapView.getCameraState();
mapView.restoreCameraState(camera, animated);
mapView.onCameraChange(handler);
```

Run: `cd frontend && npm run test:frontend`

Expected: TypeScript fails because the `LabelerMap` interface does not expose these APIs.

- [ ] **Step 2: Implement map APIs**

Add `MapCameraState`, import `MapSyncView`, `DistanceRange`, `ScreenSample`, and `computeVisibleDistanceRangeFromScreen`, then expose:

```ts
syncToSegmentRange(syncView: MapSyncView, animated: boolean): void;
getVisibleSegmentRange(payload: SegmentPayload): DistanceRange | null;
onCameraChange(handler: () => void): () => void;
getCameraState(): MapCameraState;
restoreCameraState(camera: MapCameraState, animated: boolean): void;
```

Use `map._cameraForBoxAndBearing` when available, with padding suitable for the map panel, and fall back to center/bearing if it returns no camera. Project payload context samples with `map.project([lon, lat])` and clip them to the map container viewport.

- [ ] **Step 3: Run tests**

Run: `cd frontend && npm run test:frontend`

Expected: all frontend tests pass or the next compile error points to main wiring still in progress.

## Task 4: Main Sync State

**Files:**
- Modify: `frontend/src/main.ts`
- Modify: `frontend/index.html`

- [ ] **Step 1: Add the sync control to HTML**

Add a button to the `.actions` group:

```html
<button type="button" id="sync-with-map" aria-pressed="false" disabled>Sync with Map</button>
```

- [ ] **Step 2: Implement main wiring**

In `main.ts`, add:

```ts
const syncWithMapButton = requireButton("sync-with-map");
let fullProfileRange: DistanceRange | null = null;
let currentProfileRange: DistanceRange | null = null;
let restoreCameraState: MapCameraState | null = null;
let removeMapCameraListener: (() => void) | null = null;
let ignoreNextMapCameraChange = false;
let ignoreProfileRelayout = false;
```

Implement helpers for `syncMapToProfile`, `handleProfileRelayout`, `syncProfileToMapView`, `enableMapSync`, `disableMapSync`, `rangesAreClose`, and `updateSyncWithMapButton`.

Update segment/beam selection to set `fullProfileRange`, `currentProfileRange`, and call `syncMapToProfile(true)` after profile rendering when sync is enabled.

Pass `handleProfileRelayout` into `renderProfile`.

- [ ] **Step 3: Run tests**

Run: `cd frontend && npm run test:frontend`

Expected: all frontend tests pass.

## Task 5: Layout Update

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Update HTML structure**

Wrap existing panels as:

```html
<div id="app">
  <section class="left-column">
    <section class="control-column">
      <header class="app-title"></header>
      <section class="setup-panel" id="setup-panel"></section>
      <section class="toolbar" aria-label="Label controls"></section>
      <section class="status-row"></section>
    </section>
    <section class="picker-column">
      <section class="picker-pane">
        <h2 id="file-heading">Files</h2>
        <div id="file-list" class="segment-list"></div>
      </section>
      <section class="picker-pane">
        <h2 id="beam-heading">Beams</h2>
        <div id="beam-list" class="segment-list"></div>
      </section>
    </section>
  </section>
  <section class="workspace-column">
    <section class="map-column">
      <div id="map" class="map-panel"></div>
    </section>
    <section class="profile-row">
      <div id="profile" class="profile-panel"></div>
    </section>
  </section>
</div>
```

- [ ] **Step 2: Update CSS grid**

Make `#app` a two-column grid:

```css
#app {
  display: grid;
  grid-template-columns: minmax(320px, 25vw) minmax(0, 1fr);
  height: 100vh;
  min-width: 1120px;
}
```

Make `.left-column` and `.workspace-column` stacked grids, preserve scroll behavior, and style `#sync-with-map` consistently with other toolbar buttons.

- [ ] **Step 3: Run build/tests**

Run: `cd frontend && npm run test:frontend`

Expected: all frontend tests pass.

Run: `cd frontend && npm run build`

Expected: TypeScript and Vite build complete successfully.

## Task 6: Browser Verification

**Files:**
- No source files.

- [ ] **Step 1: Start dev server**

Run: `cd frontend && npm run dev -- --port 5173`

Expected: Vite serves the app on `http://127.0.0.1:5173`.

- [ ] **Step 2: Inspect the app**

Open the local URL in the in-app browser and verify:

- left controls and files/beams are stacked,
- map/profile are stacked on the right,
- `Sync with Map` is off by default,
- no obvious text overlap or blank map/profile containers.

- [ ] **Step 3: Stop dev server**

Stop the Vite process after verification.
