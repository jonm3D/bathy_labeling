import assert from "node:assert/strict";
import test from "node:test";

import { buildProfilePlotConfig, PROFILE_DEFAULT_DRAGMODE } from "../../frontend/src/profileControls.js";

test("profile plot config enables scroll zoom and uses custom home reset", () => {
  let clicked = false;
  const config = buildProfilePlotConfig(() => {
    clicked = true;
  });

  assert.equal(config.scrollZoom, true);
  assert.equal(PROFILE_DEFAULT_DRAGMODE, "zoom");
  assert.equal(config.displaylogo, false);
  assert.equal(config.responsive, true);
  assert.ok(config.modeBarButtonsToRemove.includes("toImage"));
  assert.ok(config.modeBarButtonsToRemove.includes("autoScale2d"));
  assert.ok(config.modeBarButtonsToRemove.includes("resetScale2d"));
  assert.equal(config.modeBarButtonsToAdd.length, 1);
  assert.equal(config.modeBarButtonsToAdd[0].name, "Home");

  config.modeBarButtonsToAdd[0].click();

  assert.equal(clicked, true);
});
