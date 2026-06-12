# ATL24 Smart Labeler Design

Date: 2026-06-12

## Purpose

Design a local, single-user annotation workflow for producing photon-level training labels for an ICESat-2 bathymetry classifier. The classifier is intended to operate on top of ATL24 HDF5 data when users find that ATL24 has missed bathymetry or misclassified bathymetric photons. The labeler should use ATL24 HDF5 data access, coordinates, metadata, water-surface estimates, and corrected heights, but it must not treat ATL24 photon classes or confidence values as ground-truth labels.

The current TransectView viewer is a useful reference implementation for fast local HDF5 loading, map/profile coordination, and responsive rendering. The labeler may eventually live in a separate repository. Treat the viewer as a UI and data-access reference, not as the labeler's persistence or task-management design.

The tool should let a user review deterministically assigned photon scenes, seed a small number of labels, generate a deterministic smart-label proposal for the remaining photons, correct the result quickly, and export a training dataset that can be mapped back to the original HDF5 data.

## Core Principles

- Segment generation is controlled by the labeler, not by the annotator.
- Given the same source HDF5 files and the same segment configuration, segment generation is deterministic.
- The annotator sees enough surrounding track context to make good labels, but labels are stored only for the assigned segment.
- Feature code operates on local photon neighborhoods, not absolute along-track position or full downloaded-track length.
- ATL24 `class_ph`, `confidence`, and `low_confidence_flag` are not default v1 training features and are not used as labels.
- ATL24 remains the source product for v1. The labeler uses user-provided ATL24-like HDF5 files matching the current example data shape rather than querying SlideRule during labeling.
- ATL24 remains useful for file organization, photon metadata, coordinates, water-surface estimates, and built-in height/refraction corrections.
- ATL24 water-surface returns and `surface_h` are acceptable product assumptions for v1. The classifier is primarily a corrective layer for missing or misclassified bathymetry, not a replacement for ATL24's water-surface detection.
- Label state is stored in portable sidecar files next to the labeling project, with lightweight metadata for reload, validation, and revision safety.
- Source folder organization may encode AOI names or source collections, but those names are metadata for analysis and export, not model features.
- The first version is local and single-user. Multi-annotator assignment, adjudication, and server-backed collaboration are out of scope.

## Label Schema

Final photon labels are:

- `surface`
- `bathy`
- `land`
- `noise`
- `ambiguous`

`surface` means photons associated with laser returns from the water surface, typically a flat or wavy surface return.

`bathy` means photons associated with laser returns from the seabed.

`land` means dry surfaces, including beach above the water surface, terrain, vegetation, and built structures.

`noise` means photons associated with background noise, water-column returns, atmospheric effects, or any other photons not classified as `surface`, `bathy`, `land`, or `ambiguous`.

`ambiguous` is a valid final label but should be rare. It is intended for cases where ultra-shallow bathymetry and water-surface returns come together enough that assigning `surface` or `bathy` would be guessing, especially in reef settings. It can also be used at shorelines or other land-water interfaces where assigning `land`, `surface`, or `bathy` would be unreliable. The smart-label proposal should not create `ambiguous` labels unless the user explicitly seeded or edited photons as `ambiguous`.

`unlabeled` is an editing state, not a final training label. A completed sidecar must assign every photon inside the segment to one of the final labels. If the user does not want to finish a segment, the segment should remain `draft` or be marked outside the current training export until it has a complete sidecar.

## Segment Inventory

The user points the labeler at a folder of ATL24-like HDF5 files. On load, the project scans the folder, discovers valid ATL24 beam groups, and builds a deterministic inventory of non-overlapping 10 km labeling segments. The inventory stores enough information to reproduce segment identity and detect source changes:

- project identifier
- segment configuration version
- source root or source collection name
- optional source folder or AOI-like label inferred from the source file's parent folder under the source root
- stable source file identifier
- file name and relative path
- source file parent directory relative to the source root
- file size and modification time
- optional content hash when affordable
- ATL24 granule metadata where available, such as RGT, cycle, orbit, and acquisition start/end time
- available beam names
- beam photon counts
- beam `x_atc` min/max
- beam day/night classification from ATL24 `night_flag`
- beam strength classification from beam name and `orbit_info/sc_orient`
- generated segment IDs and `x_atc` bounds

The stable source file identifier should be derived from ATL24 granule identity when available, such as the granule filename plus orbit metadata. File size, modification time, and optional content hash are used to detect changes, not as the sole source identity.

The first project input mode is a directory of ATL24-like HDF5 files matching the example data shape: `gt1l` through `gt3r` beam groups when available, per-beam photon arrays, per-beam `night_flag`, and `orbit_info/sc_orient`. The user is expected to make AOI or source-collection decisions before labeling by downloading or organizing HDF5 files into folders. When an AOI-like name is useful, the labeler may infer it from the source file's parent folder under the source root.

SlideRule AOI querying, AOI polygon intersection, and GeoParquet ingestion are out of scope for v1. They can be added later as a source-harvest step, but the first implementation should preserve the current HDF5 file contract.

ATL24 `night_flag` is a per-photon beam dataset at paths such as `gt1l/night_flag`. The local ATL24 v002 data dictionary describes it as true when solar elevation was less than 5 degrees at the photon time and location. The labeler should use per-photon `night_flag` as the day/night feature and derive a segment-level day/night stratum by majority value inside the assigned segment window.

Beam strength should be derived from the example-data beam naming and `orbit_info/sc_orient`. ATLAS spots `1`, `3`, and `5` are strong; spots `2`, `4`, and `6` are weak. In forward orientation (`sc_orient == 1`), right beams are strong and left beams are weak. In backward orientation (`sc_orient == 0`), left beams are strong and right beams are weak. Transition orientation (`sc_orient == 2`) is outside v1 and should be rejected during inventory creation.

The segment inventory can be materialized as `labeler_manifest.json` for faster reloads, but the labeler should be able to rebuild it from the HDF5 folder and sidecar files. If files are added, removed, or changed, the tool rebuilds the inventory deterministically and marks any existing sidecars whose source metadata no longer matches as `stale` rather than overwriting them.

## Sampling and Task Generation

The first segment generator deterministically partitions ATL24 file-plus-beam tracks into 10 km segments from the supplied HDF5 collection. It does not intersect candidate segments with AOI polygons in v1; source folders may still be recorded as AOI-like metadata for later analysis.

The first segment generator should keep stratification simple:

- day/night
- beam strength

No other stratification variables are required for the initial design, but the inventory should preserve enough metadata for later analysis by source folder or inferred AOI label, date, file, beam, RGT, cycle, or track.

The segment length is a project-level configuration, not a user-facing choice. The initial default should be 10 km. If the source track is shorter than the configured segment length, the segment can use the full available track. Future projects can change the configured length, but the annotator should not select which part of a track becomes a training example.

Segment generation should avoid dependence on filesystem traversal quirks or random-number-generator iteration order. A recommended approach is:

1. Build non-overlapping candidate windows from each source file, beam, and configured segment length.
2. Assign each candidate a deterministic segment ID from source file identity, beam, and integer-meter `x_atc` bounds.
3. Sort candidates by source filename, beam, and `x_atc` start for stable display.
4. Compare candidates to existing label sidecars to derive status.
5. Show all labelable candidates in the sidebar unless the user filters the list.

Candidate windows should be non-overlapping by default to reduce duplicated nearby photons in the training pool. If a later project intentionally allows overlap, that choice must be explicit in the segment configuration version.

Segment display names should follow this pattern:

- `{atl24_file_stem}_{beam}_xatc_{start_m}_{end_m}`

The beam must be included in the stable segment ID because multiple beams from the same ATL24 file can cover the same `x_atc` range. If a shorter UI label omits the beam, the full segment ID should remain available in details and sidecar metadata.

Each labeling segment contains:

- `segment_id`
- inventory version
- segment configuration version
- stable source file identifier
- source file relative path
- beam
- assigned along-track start and end in source `x_atc` coordinates
- view-only context start and end in source `x_atc` coordinates
- day/night stratum from `night_flag`
- beam-strength stratum from beam name and `orbit_info/sc_orient`
- source folder or inferred AOI-like label, when available
- segment status derived from sidecar scan

Segment status values should include at least `unlabeled`, `draft`, `complete`, `stale`, and `conflict`.

`segment_id` should be deterministic from the project identifier, segment configuration version, stable source file identifier, source file relative path, beam, and assigned bounds. It should not depend on a transient local viewer ID such as `file-0`.

## Annotation View

The UI presents one 10 km labeling segment at a time in a standalone viewer inspired by the current TransectView map/profile layout.

The sidebar should show two primary segment lists:

- segments to label: `unlabeled`, `draft`, and `stale` segments that need review
- labeled segments: `complete` segments with valid sidecar files

If sidecar scanning finds multiple current sidecars for the same segment, or a sidecar whose metadata does not match the current HDF5 source, the sidebar should make the issue visible and avoid silently choosing one.

The profile view should:

- show the assigned segment prominently
- allow pan and zoom beyond the assigned segment for full-track or buffered context
- make the editable region visually clear
- store labels only for photons inside the assigned segment
- provide point size and point opacity sliders so sparse and dense 10 km segments remain readable

Context outside the assigned segment is view-only in the first version. This prevents the annotator from reshaping the sample while still allowing track context for interpreting surface, bathymetry, land transitions, and noise.

The map view should orient the selected track and local shoreline context. ATL24 class and confidence displays must be hidden by default in labeler mode. A diagnostic ATL24 comparison toggle can exist, but it must be explicit and off during normal labeling.

## Smart Labeling Workflow

The smart labeler stores three distinct annotation layers while a segment is open:

1. Seed labels: direct user inputs such as clicks, brush strokes, lasso selections, or class-specific example points.
2. Proposal labels: labels generated by the smart labeler from seed labels and photon features.
3. Final labels: user-accepted or user-corrected labels exported for training.

Only final labels and their `label_source` values are required to persist in the sidecar. Seed and proposal layers are working state for the open segment, not provenance that must be replayed after reload. When the user reopens a segment, the saved final labels become the current editable label state.

The user workflow is:

1. Open a segment from the sidebar.
2. Use the select tool to select photons for a class.
3. Click that class's assign/update button to mark the selected photons as manual labels.
4. Run smart labeling.
5. Inspect proposal labels.
6. Use the same select tool and class buttons to correct errors.
7. Click `Done` to validate that every photon in the segment has a final label and write the sidecar output.

The labeler should support segments where not all classes are present. The user should not need to seed a class that is absent from the scene.

Expected seeding behavior:

- If water surface is present, the user should seed representative `surface` photons.
- If bathymetry is present, the user should seed representative `bathy` photons.
- If land is present, the user should seed representative `land` photons.
- `noise` is conceptually always possible, but the user may or may not seed it manually.
- `ambiguous` should be seeded or edited only in rare cases where the user wants final ambiguous labels.

## Smart Proposal Contract

The first smart-label proposal should be deterministic from the segment photons, feature configuration, proposal parameters, and current seed labels.

The recommended v1 approach is a deterministic seeded clustering workflow:

1. Compute local features for photons in the assigned segment, using view-only context where needed for edge support.
2. Normalize features using a deterministic project or task-local feature-scaling rule with explicit missing-value handling.
3. Optionally project the normalized features into a scene-local PCA space to reduce correlated engineered features. PCA settings and deterministic sign conventions must be recorded with the proposal run.
4. Initialize a seeded k-means-style or centroid-based clustering model from the user's seeded classes in the current segment.
5. Keep seeded photons fixed to their manual class while assigning unseeded photons only to classes that were seeded in the current segment.
6. Use deterministic distance, margin, or cluster-support thresholds to decide which unseeded photons receive a proposed non-noise class.
7. Assign unresolved residual photons to `noise` when finalizing, unless the segment remains draft or incomplete.

The proposal must not invent `surface`, `bathy`, `land`, or `ambiguous` for classes that the user did not seed in the current segment. `noise` is the exception: the proposal should automatically assign unresolved residual photons to `noise` because `noise` is the residual class by definition. The first version does not need a setting to disable automatic residual-noise assignment.

The proposal run should record:

- proposal run ID
- algorithm name and version
- feature configuration hash
- feature scaling, PCA, clustering, and distance-threshold parameters
- created timestamp
- per-class seed counts
- proposal class counts

## Feature and Inference Design

Feature generation should be implemented as a reusable module shared by the smart labeler, training export or preparation code, and later prediction. The labeler does not need to store feature outputs in sidecars by default, but the same feature configuration and code path should be callable outside the UI. The module should accept photon arrays plus assigned/context bounds and return a deterministic feature table keyed by source photon identity, including at least `source_row` and `index_ph` when available.

The inference window and the feature-computation neighborhood are the same concept. For each target photon, feature values are computed from a local along-track and vertical neighborhood around that photon.

The classifier and smart proposal should not use:

- absolute along-track distance
- normalized distance from the downloaded track start
- total downloaded track length
- AOI identifier
- site/location identifier
- acquisition date or timestamp, except day/night
- ATL24 `class_ph`
- ATL24 `confidence`
- ATL24 `low_confidence_flag`

The initial engineered feature set should be deterministic and agnostic to semantic class names. It should describe each target photon and its local photon neighborhood without trying to pre-identify a water surface or seabed.

Allowed context features:

- `night_flag`: per-photon ATL24 `night_flag`, where `1` means solar elevation was less than 5 degrees at the photon time and location.
- `beam_strength`: derived categorical value `strong` or `weak` from beam name and `orbit_info/sc_orient`. For numeric model input, encode as `1` for strong and `0` for weak. Files with transition orientation are rejected before feature computation in v1.

Allowed point-height feature:

- `ortho_h_m`: the ATL24 orthometric product height for the photon. The ATL24 v002 user guide describes `ortho_h` as refraction-corrected orthometric height based on the EGM08 geoid, and the working v1 assumption is that ATL24 applies the useful refraction correction to photons below its detected water surface. For this labeler, treat `ortho_h` as the trusted ATL24 product height, especially for photons below the ATL24 sea-surface estimate. This intentionally accepts ATL24's water-surface-dependent refraction correction as a product assumption while still avoiding ATL24 bathymetry/noise class labels and confidence values as default model inputs.
- `surface_h_m`: the ATL24 sea-surface orthometric height estimate at the photon location. Because v1 accepts ATL24 water-surface returns as sufficiently reliable, `surface_h` may be used as a support feature.
- `dz_to_surface_m`: `ortho_h_m - surface_h_m`. Negative values are below the ATL24 sea-surface estimate. This is often more portable than raw orthometric height across AOIs, dates, and tides, but it remains an ATL24-derived feature and should be tracked as such in feature metadata.

Allowed local density features:

- Compute oriented elliptical neighborhood responses in the along-track/elevation plane around each target photon.
- For target photon `i`, let `dx = x_atc_j - x_atc_i` and `dz = ortho_h_j - ortho_h_i` for neighboring photons `j`.
- Use semi-major axes `a in {50, 100, 500}` meters and semi-minor axes `b in {1, 3, 5}` meters.
- Use slope-oriented kernels rather than large geometric angles. A slope `s = dz/dx` defines a major-axis unit vector `(1, s) / sqrt(1 + s^2)` and a minor-axis unit vector `(-s, 1) / sqrt(1 + s^2)`.
- The first slope bank should be `s in {-0.10, -0.03, 0.0, 0.03, 0.10}`. These are easier to reason about than angles like 30 or 60 degrees, which are extremely steep in an along-track/elevation plot.
- A neighbor is inside a kernel when `(u / a)^2 + (v / b)^2 <= 1`, where `u` and `v` are coordinates projected onto the major and minor unit vectors.
- The raw response is neighbor count divided by ellipse area `pi * a * b`. Exclude the target photon itself from the count. Use available-support normalization near source-track edges rather than treating missing context as empty.
- To avoid exporting a large bank of highly correlated features, compute the full response bank internally and export summaries for each semi-major axis:
  - `ellip_density_a{a}_max`: maximum density across `b` and `s`
  - `ellip_density_a{a}_mean`: mean density across `b` and `s`
  - `ellip_density_a{a}_contrast`: `max_density / (median_density + eps)`
  - `ellip_density_a{a}_best_minor_m`: semi-minor axis `b` that produced the maximum response
  - `ellip_density_a{a}_best_slope`: slope `s` that produced the maximum response

Allowed elevation-histogram features:

- For each target photon, compute local histograms of `ortho_h` for centered along-track windows of width `50`, `100`, and `500` meters.
- Use 1 meter elevation bins with globally anchored bin edges, such as integer-meter edges, so the binning is deterministic and not shifted per photon.
- Smooth histogram counts with a small deterministic kernel, such as `[1, 2, 1]`, before finding peaks.
- Find local maxima sorted by smoothed count. The second peak must be separated from the first by at least 2 meters so adjacent bins from the same mode are not treated as separate modes.
- Export these features for each window width `w`:
  - `hist_w{w}_n`: number of photons in the along-track window
  - `hist_w{w}_dz_peak1_m`: target photon height minus the largest peak elevation
  - `hist_w{w}_dz_peak2_m`: target photon height minus the second-largest separated peak elevation
  - `hist_w{w}_peak2_valid`: `1` if a separated second peak exists, otherwise `0`
  - `hist_w{w}_peak1_frac`: largest peak count divided by total window count
  - `hist_w{w}_peak2_frac`: second peak count divided by total window count, or `0` when absent
  - `hist_w{w}_peak_ratio`: `peak2_count / (peak1_count + eps)`
  - `hist_w{w}_photon_bin_frac`: count in the target photon's elevation bin divided by total window count
  - `hist_w{w}_z_quantile`: fraction of photons in the window with `ortho_h <= ortho_h_i`
  - `hist_w{w}_mode_count`: number of separated local maxima above a minimum fraction threshold, such as 5 percent of the total window count

Feature computation must avoid edge artifacts. A photon near the edge of the downloaded source track or assigned segment should still be classified as well as possible. Density and histogram features should normalize by the available neighborhood support rather than treating missing context outside the source data as empty water or noise.

The minimum useful surrounding along-track context target is approximately 1 km where available. The feature code should still produce valid features with less context, such as at source-track edges, but should not expose absolute edge position as a model feature.

## No ATL24 Label Leakage

The annotation UI may optionally provide an explicit diagnostic toggle to view ATL24 classes for comparison, but ATL24 labels must be hidden by default during labeling.

The primary training feature export should not include ATL24 `class_ph`, `confidence`, or `low_confidence_flag` as model features unless a later experiment explicitly defines a baseline-aware model variant. Because the classifier is intended to correct ATL24, diagnostic exports may include ATL24 baseline columns with explicit names such as `atl24_class_ph` and `atl24_confidence`, but those fields must be clearly separated from human labels and excluded from default model training.

Segment generation must also avoid ATL24 class or confidence leakage. For example, the segment generator should not preferentially select windows because ATL24 already classified bathymetry there.

## Sidecar Label Storage

The first version should use label sidecars as the source of truth for completed labels. A database is not required for v1. A small `labeler_manifest.json` may cache segment inventory and UI state, but the tool should recover by scanning HDF5 files and sidecars.

Recommended project artifacts:

- `labeler_manifest.json`: optional cached source inventory and segment configuration summary
- `labels/`: current label sidecars
- `labels/archive/`: timestamped backups of replaced sidecars
- `exports/`: optional merged training snapshots, such as CSV or Parquet
- `labeling_guide.md`: versioned label definitions and difficult-case rules

DuckDB or SQLite may be useful later for large-project querying, but neither needs to own live annotation state in v1.

Each completed segment should write a current label sidecar at a deterministic path such as:

- `labels/{segment_id}.labels.csv`
- `labels/{segment_id}.labels.json`

The CSV is the portable label table. It should include, at minimum:

- `source_row`: zero-based row position of the photon within the source beam arrays
- `index_ph`: the ATL24 photon index value read from the HDF5 file, not a custom labeler-generated point ID
- `lat`
- `lon`
- `ortho_h_m`
- `label`
- `label_source`: `manual` or `auto`

`manual` includes seed labels and later user edits. `auto` includes labels accepted from the smart-label proposal, including automatically assigned residual `noise`. On reload, editing a previously saved label should update that row's `label_source` to `manual`; rerunning and accepting a proposal can set affected proposal-derived rows to `auto`.

The pair of `source_row` and `index_ph` is the v1 row key for matching labels back to source photons. A per-row checksum is not required for v1. Instead, the metadata sidecar should include a segment-level checksum or count over the ordered source row or `index_ph` values so the tool can detect when a sidecar no longer matches the loaded photons.

The JSON metadata sidecar should include:

- schema version
- labeler version, when available
- labeling guide version
- source HDF5 filename and relative path
- stable source file identifier
- source file size and modification time, plus optional content hash
- beam
- `segment_id`
- assigned `x_atc` start and end
- context `x_atc` start and end, if different
- segment photon count
- source `source_row` and `index_ph` count and optional checksum of the segment's ordered row keys
- final label counts
- manual versus auto counts
- smart-label algorithm name, version, parameters, and feature configuration hash, if used
- created and updated timestamps
- status, normally `complete` after `Done`

On `Done`, the tool should require the CSV to contain exactly one row for every photon in the segment and no invalid labels. Rows should be sorted by `source_row` unless a later schema version explicitly records a different convention.

## Reloading, Revision, and Conflict Handling

The user must be able to reopen a previously labeled segment and revise labels.

On startup, the labeler should scan the HDF5 folder and `labels/` folder:

1. Rebuild the deterministic segment inventory from HDF5 files.
2. Read each label metadata sidecar.
3. Match sidecars to segments by `segment_id`, source file identity, beam, and `x_atc` bounds.
4. Validate sidecar completeness by row count, legal label values, and optional row-key checksum.
5. Assign each segment a status for the sidebar.

Status rules:

- `unlabeled`: no matching sidecar exists.
- `draft`: a sidecar exists but is marked draft or is incomplete.
- `complete`: a matching sidecar exists and passes validation.
- `stale`: a sidecar exists for a segment ID, but the source file identity, file metadata, segment bounds, photon count, or row-key checksum no longer matches the current HDF5 data.
- `conflict`: multiple current sidecars claim the same segment.

When opening a `complete` segment, the tool should load labels from the sidecar and allow editing. The loaded labels are treated as the current final label state; the original seed and proposal working layers do not need to be reconstructed. When saving over an existing complete sidecar, the tool should use optimistic checks: if the current sidecar on disk has changed since the segment was opened, the user must reload or intentionally overwrite. If it has not changed, the tool should archive the previous CSV and JSON to `labels/archive/{segment_id}/{timestamp}/` and then atomically replace the current sidecars.

The UI should make unsaved edits clear and provide undo or a similarly safe correction path for high-volume labeling.

## Labeling Guide

The project should include a short labeling guide before large-scale annotation begins. It should define each class and give rules for common difficult cases:

- near-surface returns and wave troughs
- ultra-shallow reef cases where `surface` and `bathy` collapse into `ambiguous`
- shoreline and land-water interface cases where `land`, `surface`, or `bathy` are not reliably separable
- sparse possible bathymetry
- dense surface-only tracks
- land-water transitions
- daylight noise
- water-column returns
- extinction-depth cases
- when to use `noise`
- when to use `ambiguous`

The guide should be versioned with the dataset because label meanings can drift over time. Each completed sidecar metadata file should record the guide version used.

## Annotation Metrics

The tool should track lightweight annotation metrics:

- task opened timestamp
- task saved timestamp
- elapsed labeling time
- number of seed labels
- number of proposal labels accepted
- number of manual edits after proposal
- final class counts
- manual versus automatic label counts

These metrics are not model features. They are used to estimate labeling speed, identify difficult scenes, and improve the annotation workflow.

## Model Training Handoff

The labeler does not need to manage train, validation, and test pools in the first version. It should export labeled data and segment metadata cleanly enough that a separate trainer can split by source folder or inferred AOI label, date, file, beam, track, inventory version, or segment configuration version.

The trainer should avoid random photon-level splits because nearby photons from the same scene are strongly correlated.

Training exports can be generated by concatenating valid current sidecar CSV files and joining their JSON metadata onto each row. Export formats can start as CSV for readability and later add Parquet for scale. The export should include label provenance fields so training can include or exclude automatic labels if needed. Feature tables for training or prediction should be generated by the reusable feature module rather than copied from stale sidecar output.

## Out of Scope for This Design

- Implementation plan
- Deep model architecture selection
- Active-learning task queues
- AOI polygon ingestion or intersection inside the labeler
- Complex multi-pool dataset management
- Training/validation/test split automation inside the labeler
- Using ATL24 labels or confidence values as default model inputs
- Letting the annotator choose arbitrary training samples from a source folder or AOI-like collection
- Multi-user task assignment, adjudication, or cloud synchronization
- Requiring SQLite, DuckDB, or another database for live annotation state

## Acceptance Criteria

This design is ready for implementation planning when:

- The input contract assumes ATL24-like HDF5 files matching the example data shape, including `gt*` beam groups, per-beam `night_flag`, and `orbit_info/sc_orient`.
- The design treats the classifier as a corrective layer on top of ATL24 HDF5 data, not a raw ATL03 or SlideRule GeoParquet workflow.
- The segment inventory deterministically creates non-overlapping 10 km HDF5 file-plus-beam segments with stable IDs.
- The annotation UI shows a sidebar with segments to label and labeled segments, plus the assigned segment with broader track context available for viewing.
- The annotator can select photons, assign or update class labels, generate a deterministic seeded clustering proposal, edit labels, and click `Done`.
- A complete sidecar assigns every photon in the segment to one final label; no `unlabeled` photons are exported.
- Final label rows include `source_row`, ATL24 HDF5 `index_ph`, `lat`, `lon`, `ortho_h_m`, `label`, and `label_source` as required fields.
- Sidecar metadata maps labels back to source HDF5 file, beam, segment bounds, and source validation checks.
- Existing labels are loaded from sidecars, validated, shown in the sidebar, and revised using archive-before-replace behavior.
- Feature generation is designed as a reusable module for smart labeling, training preparation, and later prediction.
- Feature and model design explicitly avoid absolute along-track position, track length, AOI/site identity, acquisition date beyond day/night, and default ATL24 classification/confidence leakage, while allowing ATL24 `ortho_h` and `surface_h` as trusted product-height inputs.
