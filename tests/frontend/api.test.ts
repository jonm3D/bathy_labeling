import assert from "node:assert/strict";
import test from "node:test";

import {
  buildReprocessBeamUrl,
  buildReviewTrackUrl,
  fetchManifest,
} from "../../frontend/src/api.js";

test("reprocess beam url encodes source paths safely", () => {
  assert.equal(
    buildReprocessBeamUrl("Guam/ATL24 sample.h5", "gt1l"),
    "/reprocess/beam?source=Guam%2FATL24+sample.h5&beam=gt1l",
  );
});

test("review track url encodes site and track keys safely", () => {
  assert.equal(
    buildReviewTrackUrl("Lauderdale site", "rgt_0123_cycle_07_spot_1"),
    "/review/track?source=Lauderdale+site&track=rgt_0123_cycle_07_spot_1",
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
