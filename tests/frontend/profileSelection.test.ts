import assert from "node:assert/strict";
import test from "node:test";

import { plotlyClearSelectionUpdate, plotlySelectionVisibilityStyle } from "../../frontend/src/profileSelection.js";

test("plotly selection styling keeps unselected points visible", () => {
  assert.deepEqual(plotlySelectionVisibilityStyle(0.82), {
    selectedpoints: null,
    selected: { marker: { opacity: 0.82 } },
    unselected: { marker: { opacity: 0.82 } },
  });
});

test("plotly clear selection update resets each rendered trace", () => {
  assert.deepEqual(plotlyClearSelectionUpdate(4), {
    selectedpoints: [null, null, null, null],
  });
});
