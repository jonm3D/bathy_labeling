import assert from "node:assert/strict";
import test from "node:test";

import {
  addRecentPath,
  datasetSummaryText,
  emptyBeamSelectionDetail,
  evaluateDatasetDraft,
  labelHistoryCanRedo,
  labelHistoryCanUndo,
  labelHistoryRedo,
  labelHistorySnapshot,
  labelHistoryUndo,
  pushLabelHistory,
  shortcutActionForKey,
  selectionDetailText,
} from "../../frontend/src/workflowUi.js";
import type { LabelRow } from "../../frontend/src/types.js";

test("dataset draft suggests output and enables load for an absolute input path", () => {
  assert.deepEqual(evaluateDatasetDraft("/data/ATL24", "", ""), {
    inputPath: "/data/ATL24",
    outputPath: "/data/ATL24_labeled",
    demPath: "",
    suggestedOutputPath: "/data/ATL24_labeled",
    canLoad: true,
    message: "Ready to load",
    fieldErrors: {},
  });
});

test("dataset draft blocks missing and relative paths before loading", () => {
  assert.equal(evaluateDatasetDraft("", "", "").message, "Enter an ATL24 input folder");
  assert.deepEqual(evaluateDatasetDraft("", "", "").fieldErrors, {
    input: "Enter an ATL24 input folder",
  });
  assert.equal(evaluateDatasetDraft("data/ATL24", "", "").message, "Use an absolute ATL24 input path");
  assert.equal(evaluateDatasetDraft("/data/ATL24", "labeled", "").message, "Use an absolute output path");
  assert.equal(evaluateDatasetDraft("/data/ATL24", "", "dem.tif").message, "Use an absolute DEM path or leave it blank");
});

test("recent paths move the newest non-empty path to the front and stay capped", () => {
  assert.deepEqual(addRecentPath(["/old", "/recent", "/older"], " /old ", 3), ["/old", "/recent", "/older"]);
  assert.deepEqual(addRecentPath(["/old", "/recent", "/older"], "/new", 3), ["/new", "/old", "/recent"]);
  assert.deepEqual(addRecentPath(["/old"], " ", 3), ["/old"]);
});

test("dataset summary names loaded paths without keeping the full form open", () => {
  assert.equal(
    datasetSummaryText("/data/ATL24", "/data/ATL24_labeled", "/data/reference_dem.tif"),
    "ATL24 -> ATL24_labeled | DEM reference_dem.tif",
  );
  assert.equal(datasetSummaryText("/data/ATL24", "/data/ATL24_labeled", ""), "ATL24 -> ATL24_labeled");
});

test("selection detail summarizes photon and label counts for the active beam", () => {
  const labels: LabelRow[] = [
    { source_row: 1, label: "surface", label_source: "auto" },
    { source_row: 2, label: "bathy", label_source: "manual" },
    { source_row: 3, label: "no_label", label_source: "auto" },
    { source_row: 4, label: "no_label", label_source: "manual" },
  ];

  assert.equal(selectionDetailText(1284, labels), "1,284 photons | Surface 1 | Bathy 1 | Unlabeled 2");
  assert.equal(
    selectionDetailText(1284, labels, "dirty"),
    "1,284 photons | Surface 1 | Bathy 1 | Unlabeled 2 | Unsaved changes",
  );
  assert.equal(
    selectionDetailText(1284, labels, "saved"),
    "1,284 photons | Surface 1 | Bathy 1 | Unlabeled 2 | Saved",
  );
});

test("empty beam selection detail tells the user the next action", () => {
  assert.equal(emptyBeamSelectionDetail(), "Click a beam to edit labels");
});

test("label history supports undo and redo snapshots without mutating the caller rows", () => {
  const initial: LabelRow[] = [{ source_row: 1, label: "no_label", label_source: "auto" }];
  const changed: LabelRow[] = [{ source_row: 1, label: "bathy", label_source: "manual" }];
  let history = labelHistorySnapshot(initial);

  history = pushLabelHistory(history, initial, changed);
  assert.equal(labelHistoryCanUndo(history), true);
  assert.equal(labelHistoryCanRedo(history), false);

  const undone = labelHistoryUndo(history, changed);
  assert.deepEqual(undone.labels, initial);
  assert.equal(labelHistoryCanRedo(undone.history), true);

  const redone = labelHistoryRedo(undone.history, undone.labels);
  assert.deepEqual(redone.labels, changed);

  changed[0].label = "surface";
  assert.deepEqual(redone.labels, [{ source_row: 1, label: "bathy", label_source: "manual" }]);
});

test("shortcut mapping ignores text entry and maps labeling accelerators", () => {
  assert.equal(shortcutActionForKey({ key: "1", targetTagName: "body" }), "label_surface");
  assert.equal(shortcutActionForKey({ key: "2", targetTagName: "body" }), "label_bathy");
  assert.equal(shortcutActionForKey({ key: "3", targetTagName: "body" }), "label_erase");
  assert.equal(shortcutActionForKey({ key: "Escape", targetTagName: "body" }), "escape");
  assert.equal(shortcutActionForKey({ key: "s", metaKey: true, targetTagName: "body" }), "save");
  assert.equal(shortcutActionForKey({ key: "z", metaKey: true, targetTagName: "body" }), "undo");
  assert.equal(shortcutActionForKey({ key: "z", metaKey: true, shiftKey: true, targetTagName: "body" }), "redo");
  assert.equal(shortcutActionForKey({ key: "1", targetTagName: "input" }), null);
});
