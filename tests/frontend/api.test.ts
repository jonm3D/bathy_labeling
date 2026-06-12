import assert from "node:assert/strict";
import test from "node:test";

import { buildLabelsUrl, buildProposalUrl, buildSegmentUrl } from "../../frontend/src/api.js";

test("segment urls encode ids safely", () => {
  assert.equal(buildSegmentUrl("file/beam x"), "/segments/file%2Fbeam%20x");
  assert.equal(buildLabelsUrl("file/beam x"), "/segments/file%2Fbeam%20x/labels");
  assert.equal(buildProposalUrl("file/beam x"), "/segments/file%2Fbeam%20x/proposal");
});
