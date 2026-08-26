import type { ReprocessBeamStatus, ReprocessFileStatus, ReprocessLabelOrigin, ReprocessSource } from "./types.js";

export function reprocessFileStatusClass(status: ReprocessFileStatus): string {
  return statusClass(status);
}

export function reprocessBeamStatusClass(status: ReprocessBeamStatus): string {
  return statusClass(status);
}

export function reprocessFileStatusText(source: ReprocessSource): string {
  if (source.invalid_beam_count > 0) {
    return `invalid output · ${source.invalid_beam_count}/${source.beam_count} beams`;
  }
  return `${source.status} · ${source.completed_beam_count}/${source.beam_count} beams`;
}

export function reprocessBeamStatusText(status: ReprocessBeamStatus): string {
  return status === "invalid" ? "invalid output" : status;
}

export function labelOriginStatusText(origin: ReprocessLabelOrigin): string {
  if (origin === "manual_output") {
    return "Loaded manual output labels";
  }
  return origin === "atl24_original" ? "Loaded original ATL24 labels" : "Loaded unclassified raw photons";
}

function statusClass(status: ReprocessFileStatus): string {
  return `is-status-${status}`;
}
