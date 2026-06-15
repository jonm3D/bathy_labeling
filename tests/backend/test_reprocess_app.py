from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from bathy_labeler.backend.app import create_reprocess_app
from bathy_labeler.backend.reprocess import ReprocessSession

from tests.backend.test_hdf5_store import write_atl24_like_file

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin


def make_client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    write_atl24_like_file(input_dir / "ATL24_sample.h5")
    session = ReprocessSession()
    return TestClient(create_reprocess_app(session=session)), input_dir, output_dir


def write_reference_dem(path: Path) -> None:
    data = np.full((100, 240), 3.5, dtype=np.float32)
    transform = from_origin(-145.0, 14.0, 0.01, 0.01)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
    ) as dataset:
        dataset.write(data, 1)


def test_reprocess_session_endpoints_configure_load_propose_reset_and_save(tmp_path: Path) -> None:
    client, input_dir, output_dir = make_client(tmp_path)

    configure = client.post(
        "/reprocess/session",
        json={"input_dir": str(input_dir), "output_dir": str(output_dir)},
    )
    assert configure.status_code == 200
    assert configure.json()["configured"]

    sources = client.get("/reprocess/sources")
    assert sources.status_code == 200
    source = sources.json()["sources"][0]
    assert source["source_relative_path"] == "ATL24_sample.h5"
    assert source["beams"] == ["gt1l", "gt1r"]

    beam = client.get("/reprocess/beam", params={"source": "ATL24_sample.h5", "beam": "gt1l"})
    assert beam.status_code == 200
    beam_payload = beam.json()
    assert beam_payload["beam"]["photon_count"] == 150
    assert beam_payload["labels"][0]["label"] == "surface"

    proposal = client.post(
        "/reprocess/proposal",
        json={
            "source": "ATL24_sample.h5",
            "beam": "gt1l",
            "seeds": [
                {"source_row": 0, "label": "surface", "label_source": "manual"},
                {"source_row": 149, "label": "bathy", "label_source": "manual"},
            ],
        },
    )
    assert proposal.status_code == 200
    assert proposal.json()["rows"][-1]["label_source"] == "manual"

    reset = client.post("/reprocess/reset", json={"source": "ATL24_sample.h5", "beam": "gt1l"})
    assert reset.status_code == 200
    assert reset.json()["rows"][149]["label"] == "no_label"

    save = client.post(
        "/reprocess/save",
        json={
            "source": "ATL24_sample.h5",
            "beam_labels": {
                "gt1l": [
                    {"source_row": 0, "label": "bathy", "label_source": "manual"},
                    *beam_payload["labels"][1:],
                ]
            },
        },
    )
    assert save.status_code == 200
    assert save.json()["written_beams"] == ["gt1l"]
    assert Path(save.json()["outputs"][0]["output_path"]).name == "ATL24_sample_gt1l_manual.h5"


def test_reprocess_dem_sample_endpoint_returns_reference_profile(tmp_path: Path) -> None:
    client, input_dir, output_dir = make_client(tmp_path)
    dem_path = tmp_path / "reference_dem.tif"
    write_reference_dem(dem_path)
    configure = client.post(
        "/reprocess/session",
        json={"input_dir": str(input_dir), "output_dir": str(output_dir)},
    )
    assert configure.status_code == 200

    response = client.post(
        "/reprocess/dem-sample",
        json={"source": "ATL24_sample.h5", "beam": "gt1l", "dem_path": str(dem_path)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "ATL24_sample.h5"
    assert payload["beam"] == "gt1l"
    assert payload["dem"]["dem_name"] == "reference_dem.tif"
    assert payload["dem"]["sample_count"] == 150
    assert payload["dem"]["valid_count"] == 150
    assert payload["dem"]["x_atc_m"][:3] == [0.0, 100.0, 200.0]
    assert payload["dem"]["dem_h_m"][:3] == [3.5, 3.5, 3.5]
