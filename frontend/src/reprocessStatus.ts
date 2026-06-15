import type { ReprocessBeamStatus, ReprocessFileStatus, ReprocessLabelOrigin, ReprocessSource } from "./types.js";

export function reprocessFileStatusClass(status: ReprocessFileStatus): string {
  return statusClass(status);
}

export function reprocessBeamStatusClass(status: ReprocessBeamStatus): string {
  return statusClass(status);
}

export function reprocessFileStatusText(source: ReprocessSource): string {
  return `${source.status} · ${source.completed_beam_count}/${source.beam_count} beams`;
}

export function reprocessBeamStatusText(status: ReprocessBeamStatus): string {
  return status;
}

export function labelOriginStatusText(origin: ReprocessLabelOrigin): string {
  return origin === "manual_output" ? "Loaded manual output labels" : "Loaded original ATL24 labels";
}

function statusClass(status: ReprocessFileStatus): string {
  return `is-status-${status}`;
}
