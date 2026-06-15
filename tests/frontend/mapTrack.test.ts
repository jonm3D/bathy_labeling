import assert from "node:assert/strict";
import test from "node:test";

import { boundsForCoordinates } from "../../frontend/src/mapTrack.js";

test("map track bounds cover all coordinates", () => {
  assert.deepEqual(boundsForCoordinates([[144.8, 13.4], [144.9, 13.3], [144.7, 13.5]]), [
    [144.7, 13.3],
    [144.9, 13.5],
  ]);
});

test("map track bounds return null for empty tracks", () => {
  assert.equal(boundsForCoordinates([]), null);
});
