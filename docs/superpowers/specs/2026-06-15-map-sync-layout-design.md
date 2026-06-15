# Map Sync and Labeler Layout Design

Date: 2026-06-15

## Goal

Update the ATL24 Smart Labeler frontend so the navigation and labeling controls occupy one stacked column on the left, while the map and transect profile occupy a stacked column on the right. Add the `Sync with Map` behavior from `icesat2-transectview`: when enabled, the map and profile keep their along-track spans aligned bidirectionally.

## User Experience

The app keeps the same labeling workflow and visual style. The left side becomes the operational column: setup, label tools, status, and the files/beams picker. The files and beams picker moves below the label tools rather than sitting as a separate middle column. Within that lower-left picker area, files and beams remain side by side so source selection and beam selection are both visible.

The right side becomes the viewing column. The map sits above the transect profile, and both fill the available width to make the geographic and height views easier to compare vertically. The right column should use most of the horizontal space, roughly three quarters of the app at normal desktop widths.

`Sync with Map` is an off-by-default toggle in the label toolbar. When enabled with a beam or segment loaded, the map camera follows the profile's current x-axis range. The selected track span is framed and rotated so the along-track direction reads horizontally in the map. When the user pans or zooms the profile, the map updates to the same along-track span. When the user pans, zooms, or rotates the map, the profile x-axis updates to the currently visible along-track span of the selected track.

When sync is disabled, the map restores the camera state that was active when sync was enabled. If sync is enabled before a beam or segment is loaded, it waits for the next loaded payload and then syncs.

## Architecture

Add a pure frontend helper module, `frontend/src/mapSync.ts`, for all geometry and range calculations. The helper accepts the existing `SegmentPayload` shape and works from `context.x_atc_m`, `context.lon`, and `context.lat`. It returns a normalized x-range in kilometers, interpolated geographic endpoints, a center point, and a bearing that rotates the visible track span horizontally.

Extend `frontend/src/profilePlot.ts` so the main app can subscribe to Plotly x-axis relayout changes and programmatically set the x-axis range. The existing profile rendering remains responsible for traces, selections, range persistence, and Plotly configuration.

Extend `frontend/src/mapView.ts` so the map can:

- sync the camera to a computed track span,
- project current track samples to screen coordinates,
- compute the along-track range visible in the map viewport,
- save and restore camera state,
- expose map camera-change events.

`frontend/src/main.ts` owns the sync toggle state because it already coordinates current payload, profile rendering, selection state, and map updates. It also owns loop guards so profile-originated map moves do not immediately cause profile updates, and map-originated profile range changes do not recursively retrigger map sync.

## Layout Design

Update `frontend/index.html` from three top columns plus one bottom profile row to two app columns:

- `.left-column`
  - existing `.control-column`
  - existing `.picker-column`
- `.workspace-column`
  - existing `.map-column`
  - existing `.profile-row`

Update `frontend/src/styles.css` so:

- `#app` is a full-height two-column grid,
- `.left-column` is a stacked grid with controls above the picker,
- `.workspace-column` is a stacked grid with map above profile,
- `.picker-column` remains internally split into files and beams,
- all scrollable lists and Plotly/MapLibre containers retain stable min-height and overflow behavior.

## Map Sync Behavior

The profile x-axis uses kilometers. The map helper converts `context.x_atc_m` to kilometers, filters invalid samples, sorts by distance, and interpolates endpoints for the current requested range.

Requested ranges are normalized by sorting endpoints, preserving out-of-track ranges for extrapolated framing, and enforcing a small minimum span so the map does not over-zoom to a point. Empty, single-point, all-invalid, or zero-span tracks do not sync.

Profile-to-map sync:

1. Read the current profile x-range from Plotly relayout events or stored profile state.
2. Compute a map sync view from the current payload.
3. Save the pre-sync map camera when sync is first enabled.
4. Use MapLibre camera fitting with the computed bearing and geographic endpoints.
5. Animate when enabling sync or loading a new payload, and jump for frequent relayout updates.

Map-to-profile sync:

1. Listen for map `moveend` while sync is enabled.
2. Project current payload samples into screen coordinates.
3. Clip the track line to the map viewport and compute the visible x-range.
4. If the visible range differs meaningfully from the current profile range, relayout the profile x-axis.
5. Suppress the paired profile relayout callback caused by that programmatic update.

## Edge Cases

- Sync toggle is disabled when no payload is available and re-enabled once a payload loads.
- A payload with fewer than two valid track samples leaves sync inert.
- Plotly reset/autorange relayout maps back to the full payload x-range.
- Reversed profile ranges are sorted before computing map camera state.
- Map-originated ranges tolerate extrapolation past the first or last sample when the viewport extends beyond the track endpoints.
- Existing label selection, classification visibility, DEM display, and profile range persistence continue to work.

## Testing

Add `tests/frontend/mapSync.test.ts` for pure sync helpers:

- full payload distance range,
- profile relayout range extraction,
- endpoint interpolation and range sorting,
- minimum-span behavior,
- unusable payloads returning `null`,
- visible-range clipping from projected screen samples,
- viewport extrapolation past endpoints.

Add focused profile tests if needed for exported range helpers. Existing frontend tests should continue to pass through `npm run test:frontend`.

Manual browser verification should confirm:

- left controls and picker stack correctly,
- map and profile stack in the right column,
- sync is off by default,
- enabling sync rotates and frames the map to the current profile span,
- profile pan/zoom updates the map,
- map pan/zoom updates the profile x-axis,
- disabling sync restores the previous map camera.
