import type { LabelRow } from "./types.js";

export interface PlotSourceRow {
  sourceRow: number;
}

export function manualSeedRowsForPlot<T extends PlotSourceRow>(labels: LabelRow[], assignedRows: T[]): T[] {
  const manualRows = new Set(
    labels.filter((row) => row.label_source === "manual").map((row) => row.source_row),
  );
  return assignedRows.filter((row) => manualRows.has(row.sourceRow));
}
