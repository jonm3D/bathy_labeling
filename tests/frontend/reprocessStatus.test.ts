import assert from "node:assert/strict";
import test from "node:test";

import {
  labelOriginStatusText,
  reprocessBeamStatusClass,
  reprocessBeamStatusText,
  reprocessFileStatusClass,
  reprocessFileStatusText,
} from "../../frontend/src/reprocessStatus.js";
import type { ReprocessSource } from "../../frontend/src/types.js";

test("reprocess file status maps to tile classes", () => {
  assert.equal(reprocessFileStatusClass("complete"), "is-status-complete");
  assert.equal(reprocessFileStatusClass("partial"), "is-status-partial");
  assert.equal(reprocessFileStatusClass("unclassified"), "is-status-unclassified");
  assert.equal(reprocessFileStatusClass("invalid"), "is-status-invalid");
});

test("reprocess beam status maps to tile classes", () => {
  assert.equal(reprocessBeamStatusClass("complete"), "is-status-complete");
  assert.equal(reprocessBeamStatusClass("unclassified"), "is-status-unclassified");
  assert.equal(reprocessBeamStatusClass("invalid"), "is-status-invalid");
});

test("reprocess file status text includes completed beam counts", () => {
  const source: ReprocessSource = {
    source_relative_path: "ATL24_sample.h5",
    file_name: "ATL24_sample.h5",
    source_label: null,
    beams: ["gt1l", "gt1r"],
    status: "partial",
    completed_beam_count: 1,
    invalid_beam_count: 0,
    beam_count: 2,
    beam_statuses: { gt1l: "complete", gt1r: "unclassified" },
  };

  assert.equal(reprocessFileStatusText(source), "partial · 1/2 beams");
});

test("reprocess beam status and label origin text are human-readable", () => {
  assert.equal(reprocessBeamStatusText("complete"), "complete");
  assert.equal(reprocessBeamStatusText("unclassified"), "unclassified");
  assert.equal(reprocessBeamStatusText("invalid"), "invalid output");
  assert.equal(labelOriginStatusText("manual_output"), "Loaded manual output labels");
  assert.equal(labelOriginStatusText("atl24_original"), "Loaded original ATL24 labels");
});
