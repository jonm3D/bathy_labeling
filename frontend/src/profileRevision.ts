import type { LabelRow } from "./types.js";

export interface ProfileRevisionSettings {
  pointSize: number;
  pointOpacity: number;
  showClassifications?: boolean;
  showDem?: boolean;
  demRevision?: string;
}

export function profileDataRevision(
  labels: LabelRow[],
  selectedRows: Set<number>,
  settings: ProfileRevisionSettings,
): string {
  let hash = 2166136261;
  hash = hashString(
    hash,
    `${settings.pointSize}:${settings.pointOpacity}:${settings.showClassifications ?? true}:${settings.showDem ?? false}:${settings.demRevision ?? ""};`,
  );

  for (const row of labels) {
    hash = hashString(hash, `${row.source_row}:${row.label}:${row.label_source};`);
  }
  for (const sourceRow of Array.from(selectedRows).sort((left, right) => left - right)) {
    hash = hashString(hash, `selected:${sourceRow};`);
  }
  return hash.toString(16);
}

function hashString(hash: number, value: string): number {
  let next = hash;
  for (let index = 0; index < value.length; index += 1) {
    next ^= value.charCodeAt(index);
    next = Math.imul(next, 16777619);
  }
  return next >>> 0;
}
