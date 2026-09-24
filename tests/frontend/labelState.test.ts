import assert from "node:assert/strict";
import test from "node:test";

import {
  acceptProposal,
  assignManualLabel,
  dirtyBeamLabelsForSource,
  labelSelectionWithMode,
  LABEL_OPTIONS,
  toggleLabelMode,
} from "../../frontend/src/labelState.js";
import type { FinalLabel, LabelRow } from "../../frontend/src/types.js";

function createDefaultLabels(sourceRows: number[], defaultLabel: FinalLabel = "no_label"): LabelRow[] {
  return sourceRows.map((sourceRow) => ({ source_row: sourceRow, label: defaultLabel, label_source: "auto" }));
}

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
    { source_row: 11, label: "no_label", label_source: "auto" },
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

test("reprocess save payload includes only dirty beams, not every viewed beam", () => {
  const source = "Guam/ATL24_sample.h5";
  const leftKey = `${source}\u0000gt1l`;
  const rightKey = `${source}\u0000gt1r`;
  const leftLabels = createDefaultLabels([1]);
  leftLabels[0] = { source_row: 1, label: "bathy", label_source: "manual" };
  const rightLabels = createDefaultLabels([2]);
  const cache = new Map([
    [leftKey, leftLabels],
    [rightKey, rightLabels],
  ]);

  const payload = dirtyBeamLabelsForSource(source, cache, new Set([leftKey]));

  assert.deepEqual(payload, { gt1l: leftLabels });
  assert.notEqual(payload.gt1l, leftLabels);
});

test("proposal residual no label can be accepted as auto", () => {
  const labels = createDefaultLabels([4]);
  const proposal: LabelRow[] = [{ source_row: 4, label: "no_label", label_source: "auto" }];

  assert.deepEqual(acceptProposal(labels, proposal), proposal);
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

test("label options are surface, bathy, and erase", () => {
  assert.deepEqual(LABEL_OPTIONS, [
    { label: "surface", text: "Surface" },
    { label: "bathy", text: "Bathy" },
    { label: "no_label", text: "Erase" },
  ]);
});
