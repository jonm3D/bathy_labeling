# Bathy Labeler

Local, single-user ICESat-2 photon classification tool.

It accepts ATL24-like HDF5, SlideRule ATL24 GeoParquet, or raw SlideRule ATL03
GeoParquet. Tracks are grouped by unique `(rgt, cycle, spot)` combinations and
can be limited to supplied AOIs with an along-track context margin. Every input
writes the same per-track GeoPackage output; source files are never modified.

The main workflow is for users who have downloaded ATL24, find the photon
classes too noisy for their purpose, and want a fast visual way to reclassify
surface, bathymetry, and no-label photons without modifying the original input
files.

## What It Does

- Scans a folder of ATL24-like `.h5` files and discovers valid `gt*` beams.
- Shows each beam on a map and along-track profile.
- Lets users select photons and assign `surface`, `bathy`, or `no_label`.
- Optionally suggests labels from user-provided seed examples.
- Optionally samples a local DEM GeoTIFF as a reference-only profile overlay.
- Saves one QGIS-ready GeoPackage per edited track.

## Output Behavior

Original input files are never modified.

Classified files are written to the output folder as:

```text
20240102_rgt1234_cycle007_spot6.gpkg
```

Each GeoPackage contains:

- `photons`: every classified photon in the track or AOI
- `bathymetry`: the subset where `class_manual == 40`

Core fields are `photon_id`, `track_index`, `acquisition_date`, `rgt`, `cycle`,
`spot`, `elevation_m`, `class_manual`, `time_labeled_utc`, and `atl24_class`.
`atl24_class` is null for raw ATL03 inputs. Other source fields are retained
with `atl24_` or `atl03_` prefixes. Manual class codes are:

- `surface` -> `41`
- `bathy` -> `40`
- `no_label` -> `0`

Photon IDs use `YYYYMMDD_RRRR_CCC_S_IIIIIIII`; the final field is the zero-based
index in the frozen source track. If an output already exists, it is copied to
`.bathy_labeler_backups/` before replacement. New outputs are written through a
temporary file and then atomically moved into place, so a failed save should not
corrupt the previous GeoPackage.

## Setup

From a checkout:

```bash
conda env create -f environment.yml
conda activate bathy-labeling
cd frontend
npm ci
npm run build
cd ..
```

If you already use `uv`, the same Python environment can be created with:

```bash
uv sync
cd frontend
npm ci
npm run build
cd ..
```

## Run

```bash
uv run --cache-dir .uv-cache bathy-labeler \
  --input /path/to/ATL24_folder \
  --output /path/to/ATL24_folder_cleaned
```

Open the local URL printed by `uvicorn`, usually:

```text
http://127.0.0.1:8787
```

For SlideRule review, provide a JSON config:

```json
{
  "context_margin_m": 1000,
  "output_dir": "data/classified",
  "sites": [
    {
      "id": "example_site",
      "name": "Example Site",
      "product": "atl24",
      "parquet": "data/example_atl24.parquet",
      "aoi": "data/example_aoi.gpkg"
    }
  ]
}
```

Set `product` to `atl03` for a raw SlideRule ATL03 GeoParquet. The input must
include `geoid` and `geoid_free2mean`. The labeler computes mean-tide EGM2008
height as `height - (geoid + geoid_free2mean)`. ATL03 photons start as
`no_label`; the corrected height is exposed as `elevation_m`, while raw
ellipsoidal height and the correction fields are retained with `atl03_`
prefixes.

Paths are resolved relative to the config file. Start the app with:

```bash
uv run --cache-dir .uv-cache bathy-labeler \
  --review-config /path/to/review.json
```

Outputs are written beneath `output_dir`, one GeoPackage per AOI-intersecting
`(rgt, cycle, spot)` track:

```text
data/classified/example_site/20240102_rgt0123_cycle007_spot1.gpkg
```

Only photons inside the AOI are saved. Context photons are display-only.

When a review site provides `site_marker`, tracks are ordered by closest photon
distance to that marker. In review mode, use Up/Down to switch sites and
Left/Right to move through tracks from nearest to farthest.

When changing frontend code, use the Vite dev server in `frontend/`:

```bash
cd frontend
npm run dev
```

## Summary figures

`bathy_labeler.summary_plots.create_site_summary_plots()` creates the default
per-site outputs from an AOI, classified-track folder, and optional reference
DEM:

- an 8 × 8 inch CartoDB Positron layout with the AOI, 60% reference DEM, manually
  labeled bathymetry, symmetric zero-centered `cmcrameri.bukavu` normalization,
  and a projection-aware metric scale bar;
- a 4 × 4 inch horizontal histogram with elevation on the vertical axis.

The map plots in a local projected CRS for the metric scale bar while formatting
its axes as longitude and latitude. Bathymetry points are drawn deepest first so
the shallowest elevations remain visually on top. Reference DEMs must already be
in EGM2008 and carry an `EGM2008`/`EGM08` `vertical_datum` GeoTIFF tag; native
datum rasters are rejected so the shared color scale cannot mix vertical
references.

## Development Checks

Python backend:

```bash
uv run --cache-dir .uv-cache pytest -q
```

Frontend:

```bash
cd frontend
npm ci
npm run test:frontend
npm run build
```

## Project Scope

The publishable product is the ATL24 cleanup/reclassification workflow.

The older sidecar training-label workflow is experimental and intentionally
hidden from the normal CLI help. It should move to a separate branch or project
before any serious ICESat-2 ML labeled-dataset effort.

## References

- [ATL24 Version 2 product page](https://nsidc.org/data/atl24/versions/2)
- [ATL24 Version 2 DOI](https://doi.org/10.5067/ATLAS/ATL24.002)

The NSIDC product page links the current ATL24 user guide, ATBD, known issues,
and data dictionary.
