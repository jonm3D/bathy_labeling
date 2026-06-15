# ATL24 Smart Labeler

Local, single-user photon labeling tool for ATL24-like HDF5 bathymetry data.

## Development

```bash
PYTHONPATH=src pytest -q
```

The frontend lives in `frontend/` once the UI scaffold is added.

## Run

Default ATL24 reprocessing mode:

```bash
bathy-labeler --input /path/to/h5-folder --output /path/to/h5-folder_labeled --port 8787
```

The default app labels whole beams/tracks and writes one ATL24-like file per
saved beam, named `original_name_beam_manual.h5`, into the selected output
folder. Original input files are never modified.

Optionally enter a local DEM GeoTIFF path in the UI and toggle `Show DEM` to
sample it along the selected beam as a reference-only transect overlay. The DEM
trace is not used for classifications, proposals, or saved H5 outputs.

Training sidecar mode:

```bash
bathy-labeler /path/to/h5-folder --training --project /path/to/label-project --port 8787
```
