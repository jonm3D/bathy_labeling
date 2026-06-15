import assert from "node:assert/strict";
import test from "node:test";

import { reprocessSaveStatusText } from "../../frontend/src/saveStatus.js";

test("save status names the single per-beam output file", () => {
  assert.equal(
    reprocessSaveStatusText({
      outputs: [{ beam: "gt1l", output_path: "/tmp/out/ATL24_sample_gt1l_manual.h5" }],
    }),
    "Saved ATL24_sample_gt1l_manual.h5",
  );
});

test("save status summarizes multiple per-beam output files", () => {
  assert.equal(
    reprocessSaveStatusText({
      outputs: [
        { beam: "gt1l", output_path: "/tmp/out/ATL24_sample_gt1l_manual.h5" },
        { beam: "gt1r", output_path: "/tmp/out/ATL24_sample_gt1r_manual.h5" },
      ],
    }),
    "Saved 2 beam H5 files",
  );
});
