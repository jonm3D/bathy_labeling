import type { FinalLabel, LabelRow } from "./types.js";

export interface DatasetDraftState {
  inputPath: string;
  outputPath: string;
  demPath: string;
  suggestedOutputPath: string;
  canLoad: boolean;
  message: string;
  fieldErrors: Partial<Record<DatasetField, string>>;
}

export type DatasetField = "input" | "output" | "dem";
export type SaveState = "dirty" | "saved" | "neutral";
export type ShortcutAction =
  | "label_surface"
  | "label_bathy"
  | "label_erase"
  | "escape"
  | "save"
  | "undo"
  | "redo";

export interface ShortcutKeyInput {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  shiftKey?: boolean;
  targetTagName?: string;
}

export interface LabelHistory {
  undo: LabelRow[][];
  redo: LabelRow[][];
}

const SUMMARY_LABEL_ORDER: FinalLabel[] = ["surface", "bathy", "no_label"];

export function evaluateDatasetDraft(inputPath: string, outputPath: string, demPath: string): DatasetDraftState {
  const input = inputPath.trim();
  const output = outputPath.trim() || defaultOutputDir(input);
  const dem = demPath.trim();
  const suggestedOutputPath = defaultOutputDir(input);
  const fieldErrors = datasetDraftFieldErrors(input, output, dem);
  const message = datasetDraftMessage(fieldErrors);

  return {
    inputPath: input,
    outputPath: output,
    demPath: dem,
    suggestedOutputPath,
    canLoad: message === "Ready to load",
    message,
    fieldErrors,
  };
}

export function defaultOutputDir(inputPath: string): string {
  const trimmed = inputPath.trim().replace(/\/+$/, "");
  return trimmed ? `${trimmed}_labeled` : "";
}

export function addRecentPath(paths: string[], path: string, limit = 5): string[] {
  const nextPath = path.trim();
  if (!nextPath) {
    return [...paths];
  }
  return [nextPath, ...paths.filter((candidate) => candidate !== nextPath)].slice(0, limit);
}

export function datasetSummaryText(inputPath: string, outputPath: string, demPath: string): string {
  const inputName = pathName(inputPath);
  const outputName = pathName(outputPath);
  const demName = pathName(demPath);
  return demName ? `${inputName} -> ${outputName} | DEM ${demName}` : `${inputName} -> ${outputName}`;
}

export function selectionDetailText(photonCount: number, labels: LabelRow[], saveState: SaveState = "neutral"): string {
  const counts = new Map<FinalLabel, number>();
  for (const row of labels) {
    counts.set(row.label, (counts.get(row.label) ?? 0) + 1);
  }
  const labelSummary = SUMMARY_LABEL_ORDER.map(
    (label) => `${labelDisplayName(label)} ${(counts.get(label) ?? 0).toLocaleString()}`,
  ).join(" | ");
  const base = `${photonCount.toLocaleString()} photons | ${labelSummary}`;
  if (saveState === "dirty") {
    return `${base} | Unsaved changes`;
  }
  if (saveState === "saved") {
    return `${base} | Saved`;
  }
  return base;
}

export function emptyBeamSelectionDetail(): string {
  return "Click a beam to edit labels";
}

export function labelDisplayName(label: FinalLabel): string {
  if (label === "no_label") {
    return "Unlabeled";
  }
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export function labelHistorySnapshot(_labels: LabelRow[]): LabelHistory {
  return { undo: [], redo: [] };
}

export function pushLabelHistory(history: LabelHistory, previousLabels: LabelRow[], nextLabels: LabelRow[]): LabelHistory {
  if (labelsEqual(previousLabels, nextLabels)) {
    return {
      undo: history.undo.map(cloneLabels),
      redo: history.redo.map(cloneLabels),
    };
  }
  return {
    undo: [...history.undo.map(cloneLabels), cloneLabels(previousLabels)],
    redo: [],
  };
}

export function labelHistoryCanUndo(history: LabelHistory): boolean {
  return history.undo.length > 0;
}

export function labelHistoryCanRedo(history: LabelHistory): boolean {
  return history.redo.length > 0;
}

export function labelHistoryUndo(history: LabelHistory, currentLabels: LabelRow[]): { history: LabelHistory; labels: LabelRow[] } {
  const previous = history.undo.at(-1);
  if (!previous) {
    return { history: { undo: history.undo.map(cloneLabels), redo: history.redo.map(cloneLabels) }, labels: cloneLabels(currentLabels) };
  }
  return {
    labels: cloneLabels(previous),
    history: {
      undo: history.undo.slice(0, -1).map(cloneLabels),
      redo: [...history.redo.map(cloneLabels), cloneLabels(currentLabels)],
    },
  };
}

export function labelHistoryRedo(history: LabelHistory, currentLabels: LabelRow[]): { history: LabelHistory; labels: LabelRow[] } {
  const next = history.redo.at(-1);
  if (!next) {
    return { history: { undo: history.undo.map(cloneLabels), redo: history.redo.map(cloneLabels) }, labels: cloneLabels(currentLabels) };
  }
  return {
    labels: cloneLabels(next),
    history: {
      undo: [...history.undo.map(cloneLabels), cloneLabels(currentLabels)],
      redo: history.redo.slice(0, -1).map(cloneLabels),
    },
  };
}

export function shortcutActionForKey(input: ShortcutKeyInput): ShortcutAction | null {
  if (isTextEntryTarget(input.targetTagName)) {
    return null;
  }
  const key = input.key.toLowerCase();
  const command = Boolean(input.metaKey || input.ctrlKey);
  if (command && key === "s") {
    return "save";
  }
  if (command && key === "z" && input.shiftKey) {
    return "redo";
  }
  if (command && key === "z") {
    return "undo";
  }
  if (input.key === "Escape") {
    return "escape";
  }
  if (key === "1") {
    return "label_surface";
  }
  if (key === "2") {
    return "label_bathy";
  }
  if (key === "3") {
    return "label_erase";
  }
  return null;
}

function datasetDraftFieldErrors(inputPath: string, outputPath: string, demPath: string): Partial<Record<DatasetField, string>> {
  const errors: Partial<Record<DatasetField, string>> = {};
  let inputIsUsable = true;
  if (!inputPath) {
    errors.input = "Enter an ATL24 input folder";
    inputIsUsable = false;
  } else if (!isAbsolutePath(inputPath)) {
    errors.input = "Use an absolute ATL24 input path";
    inputIsUsable = false;
  }
  if (!outputPath && inputIsUsable) {
    errors.output = "Choose an output path";
  } else if (outputPath && !isAbsolutePath(outputPath)) {
    errors.output = "Use an absolute output path";
  }
  if (demPath && !isAbsolutePath(demPath)) {
    errors.dem = "Use an absolute DEM path or leave it blank";
  }
  return errors;
}

function datasetDraftMessage(fieldErrors: Partial<Record<DatasetField, string>>): string {
  return fieldErrors.input ?? fieldErrors.output ?? fieldErrors.dem ?? "Ready to load";
}

function isAbsolutePath(path: string): boolean {
  return path.startsWith("/") || /^[A-Za-z]:[\\/]/.test(path);
}

function pathName(path: string): string {
  const trimmed = path.trim().replace(/[/\\]+$/, "");
  const parts = trimmed.split(/[/\\]/);
  return parts.at(-1) ?? trimmed;
}

function cloneLabels(labels: LabelRow[]): LabelRow[] {
  return labels.map((row) => ({ ...row }));
}

function labelsEqual(left: LabelRow[], right: LabelRow[]): boolean {
  return (
    left.length === right.length &&
    left.every((row, index) => {
      const candidate = right[index];
      return (
        candidate !== undefined &&
        row.source_row === candidate.source_row &&
        row.label === candidate.label &&
        row.label_source === candidate.label_source
      );
    })
  );
}

function isTextEntryTarget(tagName: string | undefined): boolean {
  return tagName === "input" || tagName === "textarea" || tagName === "select";
}
