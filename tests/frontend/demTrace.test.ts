import assert from "node:assert/strict";
import test from "node:test";

import { profileDemTracePoints } from "../../frontend/src/demTrace.js";
import type { DemSamplePayload } from "../../frontend/src/types.js";

const sample: DemSamplePayload = {
  source: "ATL24_sample.h5",
  beam: "gt1l",
  dem: {
    dem_path: "/tmp/reference.tif",
    dem_name: "reference.tif",
    crs: "EPSG:32655",
    x_atc_m: [0, 100, 200, 300],
    dem_h_m: [1.5, null, Number.NaN, 2.5],
    sample_count: 4,
    valid_count: 2,
    sampling_method: "nearest",
  },
};

test("profile DEM trace points filter missing samples and convert x_atc to km", () => {
  assert.deepEqual(profileDemTracePoints(sample), {
    xKm: [0, 0.3],
    hM: [1.5, 2.5],
  });
});
