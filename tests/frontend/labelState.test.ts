import assert from "node:assert/strict";
import test from "node:test";

import {
  acceptProposal,
  assignManualLabel,
  createDefaultLabels,
  importAtl24Classifications,
  labelSelectionWithMode,
  labelsForAppMode,
  toggleLabelMode,
} from "../../frontend/src/labelState.js";
import type { LabelRow } from "../../frontend/src/types.js";

test("manual assignment sets selected rows to manual source", () => {
  const labels = createDefaultLabels([10, 11, 12]);

  const updated = assignManualLabel(labels, new Set([11, 12]), "bathy");

  assert.deepEqual(updated, [
    { source_row: 10, label: "no_label", label_source: "auto" },
    { source_row: 11, label: "bathy", label_source: "manual" },
    { source_row: 12, label: "bathy", label_source: "manual" },
  ]);
});

test("accepting proposal preserves manual edits", () => {
  const labels: LabelRow[] = [
    { source_row: 10, label: "bathy", label_source: "manual" },
    { source_row: 11, label: "noise", label_source: "auto" },
  ];
  const proposal: LabelRow[] = [
    { source_row: 10, label: "surface", label_source: "auto" },
    { source_row: 11, label: "surface", label_source: "auto" },
  ];

  assert.deepEqual(acceptProposal(labels, proposal), [
    { source_row: 10, label: "bathy", label_source: "manual" },
    { source_row: 11, label: "surface", label_source: "auto" },
  ]);
});

test("proposal residual no label can be accepted as auto", () => {
  const labels = createDefaultLabels([4]);
  const proposal: LabelRow[] = [{ source_row: 4, label: "no_label", label_source: "auto" }];

  assert.deepEqual(acceptProposal(labels, proposal), proposal);
});

test("importing ATL24 classifications maps known classes and preserves manual edits", () => {
  const labels: LabelRow[] = [
    { source_row: 10, label: "no_label", label_source: "auto" },
    { source_row: 11, label: "land", label_source: "manual" },
    { source_row: 12, label: "no_label", label_source: "auto" },
    { source_row: 13, label: "bathy", label_source: "auto" },
  ];

  const imported = importAtl24Classifications(labels, [41, 40, 0, 99]);

  assert.deepEqual(imported, [
    { source_row: 10, label: "surface", label_source: "auto" },
    { source_row: 11, label: "land", label_source: "manual" },
    { source_row: 12, label: "no_label", label_source: "auto" },
    { source_row: 13, label: "no_label", label_source: "auto" },
  ]);
});

test("label modes behave like a unique toggle option", () => {
  assert.equal(toggleLabelMode(null, "bathy"), "bathy");
  assert.equal(toggleLabelMode("surface", "bathy"), "bathy");
  assert.equal(toggleLabelMode("bathy", "bathy"), null);
});

test("active label mode applies manual labels to selected rows", () => {
  const labels = createDefaultLabels([20, 21, 22]);

  assert.deepEqual(labelSelectionWithMode(labels, new Set([20, 22]), "surface"), [
    { source_row: 20, label: "surface", label_source: "manual" },
    { source_row: 21, label: "no_label", label_source: "auto" },
    { source_row: 22, label: "surface", label_source: "manual" },
  ]);
  assert.deepEqual(labelSelectionWithMode(labels, new Set([20, 22]), null), labels);
});

test("default mode exposes only surface bathy and no label classes", () => {
  assert.deepEqual(labelsForAppMode("reprocess"), [
    { label: "surface", text: "Surface" },
    { label: "bathy", text: "Bathy" },
    { label: "no_label", text: "Erase" },
  ]);
});

test("training mode keeps the richer training label set", () => {
  assert.deepEqual(
    labelsForAppMode("training").map((item) => item.label),
    ["surface", "bathy", "land", "noise", "ambiguous"],
  );
});
