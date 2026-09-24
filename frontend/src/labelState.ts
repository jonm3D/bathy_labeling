import type { FinalLabel, LabelRow } from "./types.js";

export interface LabelModeOption {
  label: FinalLabel;
  text: string;
}

export const LABEL_OPTIONS: readonly LabelModeOption[] = [
  { label: "surface", text: "Surface" },
  { label: "bathy", text: "Bathy" },
  { label: "no_label", text: "Erase" },
];

export function assignManualLabel(labels: LabelRow[], selectedRows: Set<number>, label: FinalLabel): LabelRow[] {
  return labels.map((row) =>
    selectedRows.has(row.source_row)
      ? { source_row: row.source_row, label, label_source: "manual" }
      : { ...row },
  );
}

export function toggleLabelMode(currentLabel: FinalLabel | null, nextLabel: FinalLabel): FinalLabel | null {
  return currentLabel === nextLabel ? null : nextLabel;
}

export function labelSelectionWithMode(
  labels: LabelRow[],
  selectedRows: Set<number>,
  activeLabel: FinalLabel | null,
): LabelRow[] {
  return activeLabel && selectedRows.size > 0 ? assignManualLabel(labels, selectedRows, activeLabel) : labels;
}

export function acceptProposal(currentLabels: LabelRow[], proposalRows: LabelRow[]): LabelRow[] {
  const manualByRow = new Map(
    currentLabels.filter((row) => row.label_source === "manual").map((row) => [row.source_row, row]),
  );
  return proposalRows.map((proposalRow) => {
    const manual = manualByRow.get(proposalRow.source_row);
    return manual ? { ...manual } : { ...proposalRow };
  });
}

export function dirtyBeamLabelsForSource(
  source: string,
  labelCache: ReadonlyMap<string, LabelRow[]>,
  dirtySelections: ReadonlySet<string>,
): Record<string, LabelRow[]> {
  const labelsByBeam: Record<string, LabelRow[]> = {};
  for (const key of dirtySelections) {
    const [cachedSource, cachedBeam] = key.split("\u0000");
    const labels = labelCache.get(key);
    if (cachedSource === source && cachedBeam && labels) {
      labelsByBeam[cachedBeam] = labels.map((row) => ({ ...row }));
    }
  }
  return labelsByBeam;
}

export function importAtl24Classifications(
  currentLabels: LabelRow[],
  atl24ClassPh: Array<number | null | undefined>,
): LabelRow[] {
  return currentLabels.map((row, index) => {
    if (row.label_source === "manual") {
      return { ...row };
    }
    return {
      source_row: row.source_row,
      label: mapAtl24ClassToLabel(atl24ClassPh[index]),
      label_source: "auto",
    };
  });
}

function mapAtl24ClassToLabel(classPh: number | null | undefined): FinalLabel {
  if (classPh === 41) {
    return "surface";
  }
  if (classPh === 40) {
    return "bathy";
  }
  return "no_label";
}
