import type { FinalLabel, LabelRow } from "./types.js";

export type LabelModeSet = "reprocess" | "training";

export interface LabelModeOption {
  label: FinalLabel;
  text: string;
}

const REPROCESS_LABELS: LabelModeOption[] = [
  { label: "surface", text: "Surface" },
  { label: "bathy", text: "Bathy" },
  { label: "no_label", text: "No label" },
];

const TRAINING_LABELS: LabelModeOption[] = [
  { label: "surface", text: "Surface" },
  { label: "bathy", text: "Bathy" },
  { label: "land", text: "Land" },
  { label: "noise", text: "Noise" },
  { label: "ambiguous", text: "Ambiguous" },
];

export function labelsForAppMode(mode: LabelModeSet): LabelModeOption[] {
  return mode === "reprocess" ? [...REPROCESS_LABELS] : [...TRAINING_LABELS];
}

export function createDefaultLabels(sourceRows: number[], defaultLabel: FinalLabel = "no_label"): LabelRow[] {
  return sourceRows.map((sourceRow) => ({
    source_row: sourceRow,
    label: defaultLabel,
    label_source: "auto",
  }));
}

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
