import assert from "node:assert/strict";
import test from "node:test";

import { CLASS_COLORS, labelColorForClass, profilePointColor } from "../../frontend/src/profileColors.js";

test("classification colors keep bathy distinct from danger red", () => {
  assert.equal(profilePointColor("surface", true), "#0072b2");
  assert.equal(profilePointColor("bathy", true), "#d55e00");
  assert.equal(profilePointColor("no_label", true), "#8b95a1");
});

test("class color lookup exposes swatch colors for label buttons", () => {
  assert.equal(CLASS_COLORS.land, "#8f6b3f");
  assert.equal(CLASS_COLORS.no_label, "#8b95a1");
  assert.equal(labelColorForClass("ambiguous"), "#7c3aed");
});

test("grey display mode ignores classification colors", () => {
  assert.equal(profilePointColor("bathy", false), "#8d99ae");
  assert.equal(profilePointColor("surface", false), "#8d99ae");
});
