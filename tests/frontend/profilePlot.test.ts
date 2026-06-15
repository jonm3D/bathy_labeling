import assert from "node:assert/strict";
import test from "node:test";

import { manualSeedRowsForPlot } from "../../frontend/src/plotRows.js";
import type { LabelRow } from "../../frontend/src/types.js";

test("manual seed rows are separated for open-circle plot overlays", () => {
  const labels: LabelRow[] = [
    { source_row: 1, label: "surface", label_source: "auto" },
    { source_row: 2, label: "bathy", label_source: "manual" },
    { source_row: 3, label: "noise", label_source: "manual" },
  ];

  assert.deepEqual(manualSeedRowsForPlot(labels, [{ sourceRow: 1 }, { sourceRow: 2 }, { sourceRow: 3 }]), [
    { sourceRow: 2 },
    { sourceRow: 3 },
  ]);
});
