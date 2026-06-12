# ATL24 Smart Labeler

Local, single-user photon labeling tool for ATL24-like HDF5 bathymetry data.

## Development

```bash
PYTHONPATH=src pytest -q
```

The frontend lives in `frontend/` once the UI scaffold is added.

## Run

```bash
PYTHONPATH=src python -m bathy_labeler.cli /path/to/h5-folder --project /path/to/label-project --port 8787
```
