# ATL24 Bathymetry Cleaner

Local, single-user cleanup tool for ATL24-like HDF5 bathymetry files.

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
- Saves cleaned ATL24-like HDF5 outputs, one file per edited beam.

## Output Behavior

Original input files are never modified.

Cleaned files are written to the output folder as:

```text
original_name_gt1l_manual.h5
original_name_gt1r_manual.h5
```

Each saved file is copied from the original ATL24 file, then only the selected
beam's `class_ph` values are rewritten:

- `surface` -> `41`
- `bathy` -> `40`
- `no_label` -> `0`

If a cleaned output already exists, the previous file is copied to
`.bathy_labeler_backups/` before replacement. New outputs are written through a
temporary file and then atomically moved into place, so a failed save should not
corrupt the previous cleaned H5.

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

When changing frontend code, use the Vite dev server in `frontend/`:

```bash
cd frontend
npm run dev
```

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
