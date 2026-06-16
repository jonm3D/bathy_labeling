import assert from "node:assert/strict";
import test from "node:test";

import {
  buildLabelsUrl,
  buildProposalUrl,
  buildReprocessBeamUrl,
  buildSegmentUrl,
  fetchManifest,
} from "../../frontend/src/api.js";

test("segment urls encode ids safely", () => {
  assert.equal(buildSegmentUrl("file/beam x"), "/segments/file%2Fbeam%20x");
  assert.equal(buildLabelsUrl("file/beam x"), "/segments/file%2Fbeam%20x/labels");
  assert.equal(buildProposalUrl("file/beam x"), "/segments/file%2Fbeam%20x/proposal");
});

test("reprocess beam url encodes source paths safely", () => {
  assert.equal(
    buildReprocessBeamUrl("Guam/ATL24 sample.h5", "gt1l"),
    "/reprocess/beam?source=Guam%2FATL24+sample.h5&beam=gt1l",
  );
});

test("api calls reject HTML fallback responses with backend guidance", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response("<!doctype html><title>Vite fallback</title>", {
      status: 200,
      headers: { "Content-Type": "text/html" },
    });
  try {
    await assert.rejects(fetchManifest(), /Expected JSON from \/manifest; received text\/html/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
