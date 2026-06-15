import assert from "node:assert/strict";
import test from "node:test";

import { profileDataRevision } from "../../frontend/src/profileRevision.js";
import type { LabelRow } from "../../frontend/src/types.js";

const baseLabels: LabelRow[] = [
  { source_row: 1, label: "no_label", label_source: "auto" },
  { source_row: 2, label: "surface", label_source: "auto" },
];

test("profile data revision changes when labels change", () => {
  const changedLabels: LabelRow[] = [
    { source_row: 1, label: "bathy", label_source: "manual" },
    { source_row: 2, label: "surface", label_source: "auto" },
  ];

  assert.notEqual(
    profileDataRevision(baseLabels, new Set(), { pointSize: 4, pointOpacity: 0.8 }),
    profileDataRevision(changedLabels, new Set(), { pointSize: 4, pointOpacity: 0.8 }),
  );
});

test("profile data revision changes when selected rows change", () => {
  assert.notEqual(
    profileDataRevision(baseLabels, new Set(), { pointSize: 4, pointOpacity: 0.8 }),
    profileDataRevision(baseLabels, new Set([1]), { pointSize: 4, pointOpacity: 0.8 }),
  );
});
