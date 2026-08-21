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

test("map track bounds use the short span across the antimeridian", () => {
  assert.deepEqual(boundsForCoordinates([[179.8, 10], [-179.7, 11], [-179.5, 9]]), [
    [179.8, 9],
    [180.5, 11],
  ]);
});

test("map track bounds ignore invalid coordinates", () => {
  assert.deepEqual(boundsForCoordinates([[Number.NaN, 0], [144, 13], [145, 14]]), [
    [144, 13],
    [145, 14],
  ]);
});
