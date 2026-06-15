# Reprocess Output Status and Revisit Workflow Design

## Summary

Default reprocess mode should treat the output directory as the durable progress
state for batch labeling. The viewer will continue to scan original ATL24 files
from the input directory, but it will detect per-beam manual outputs in the
output directory and use them to show completion status and initialize labels
when revisiting a beam.

## Goals

- Make it obvious which files and beams have already been reclassified.
- Let users revisit a completed beam and see the relabeled output state.
- Preserve the existing per-beam output format: `original_stem_beam_manual.h5`.
- Keep original input files as the source of photon geometry and metadata.
- Avoid sidecars or a separate progress manifest in default mode.

## Completion Status Model

Completion is beam-granular. A beam is `complete` when its expected manual H5
exists in the configured output directory. A beam is `unclassified` when no
manual H5 exists.

File status is aggregated from the valid beams in the original input file:

- `complete`: every valid beam has a manual output file.
- `partial`: at least one valid beam has a manual output file, but not all.
- `unclassified`: no valid beam has a manual output file.

Status is derived from the filesystem each time the session scans or refreshes
sources. Existing `_manual.h5` files in the input directory remain ignored.

## Load Behavior

The app always reads photon geometry and non-label beam metadata from the
original ATL24 H5 in the input directory.

When a beam is selected:

- If `output_dir/original_stem_beam_manual.h5` exists, initialize working labels
  from that manual file's selected-beam `class_ph`.
- If no manual output exists, initialize working labels from the original ATL24
  file's selected-beam `class_ph`.
- The payload should include enough metadata for the UI to display whether the
  labels came from `manual_output` or `atl24_original`.

Manual output files should be validated against the original beam row count
before their labels are used. If the manual output exists but is unreadable,
missing the beam, missing `class_ph`, or has a length mismatch, the backend
should return a clear error rather than silently falling back to original labels.

## Save Behavior

Saving remains per-beam. The backend copies the original ATL24 file to
`output_dir/original_stem_beam_manual.h5` and rewrites only the selected beam's
`class_ph`. Other beams in that copied file remain identical to the original
input file.

After a successful save, the backend response should include updated beam and
file status for the saved source. The frontend should refresh the file and beam
tiles immediately so progress colors update without a page reload.

## Reset Behavior

`Reset to ATL24` restores the current in-memory working labels from the original
ATL24 file and clears manual seed markers for that beam. It does not delete any
existing manual output file. After reset, the beam can still display as complete
until the user saves the reset labels or a future explicit delete/clear action is
added.

## UI Design

File and beam selector tiles receive status classes:

- File complete: light green.
- File partial: light yellow/neutral.
- File unclassified: light red.
- Beam complete: light green.
- Beam unclassified: light red.

Tile secondary text should include compact status text such as `complete`,
`partial`, or `unclassified`. For file tiles, include a count like `2/4 beams`
when useful.

The active beam text/status line should also indicate whether loaded labels came
from manual output or original ATL24 classifications.

## Backend API Changes

`/reprocess/sources` should return status metadata for each file and beam.

Expected source shape additions:

- `status`: `complete`, `partial`, or `unclassified`.
- `completed_beam_count`: number of beams with manual outputs.
- `beam_count`: valid beam count.
- `beam_statuses`: mapping of beam name to `complete` or `unclassified`.

`/reprocess/beam` should initialize labels from manual output when present and
include label source metadata:

- `label_origin`: `manual_output` or `atl24_original`.
- `manual_output_path`: absolute path when a manual output was used, otherwise
  `null`.

`/reprocess/save` should continue returning output paths and written beams, and
should also include refreshed status for the saved source.

## Testing

Backend tests should cover:

- Source scanning reports no outputs as unclassified.
- Existing per-beam manual outputs mark beams complete and files partial or
  complete as appropriate.
- Loading a completed beam initializes labels from the manual output's `class_ph`.
- Loading an incomplete beam initializes labels from original ATL24 `class_ph`.
- Corrupt or mismatched manual outputs fail with a clear error.
- Saving updates completion status in the response.

Frontend tests should cover:

- File tile status class selection for complete, partial, and unclassified.
- Beam tile status class selection for complete and unclassified.
- Beam load status message reflects manual output versus original ATL24 labels.
- Save response refreshes status metadata used by the selectors.

## Out of Scope

- Deleting manual output files from the UI.
- Persisting manual/auto provenance in default reprocess outputs.
- Any change to training sidecar mode.
- Any change to DEM overlay sampling or display behavior.
