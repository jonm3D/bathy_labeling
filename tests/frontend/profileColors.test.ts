import assert from "node:assert/strict";
import test from "node:test";

import { profilePointColor } from "../../frontend/src/profileColors.js";

test("classification colors show bathy points in red", () => {
  assert.equal(profilePointColor("bathy", true), "#ef4444");
});

test("grey display mode ignores classification colors", () => {
  assert.equal(profilePointColor("bathy", false), "#8d99ae");
  assert.equal(profilePointColor("surface", false), "#8d99ae");
});
