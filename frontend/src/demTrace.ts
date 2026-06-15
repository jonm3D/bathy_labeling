import type { DemSamplePayload } from "./types.js";

export interface DemTracePoints {
  xKm: number[];
  hM: number[];
}

export function profileDemTracePoints(payload: DemSamplePayload): DemTracePoints {
  const xKm: number[] = [];
  const hM: number[] = [];
  payload.dem.dem_h_m.forEach((height, index) => {
    if (typeof height !== "number" || !Number.isFinite(height)) {
      return;
    }
    xKm.push(payload.dem.x_atc_m[index] / 1000);
    hM.push(height);
  });
  return { xKm, hM };
}

export function demSampleRevision(payload: DemSamplePayload | null): string {
  if (!payload) {
    return "";
  }
  return [
    payload.source,
    payload.beam,
    payload.dem.dem_path,
    payload.dem.sample_count,
    payload.dem.valid_count,
    payload.dem.x_atc_m.length,
    payload.dem.dem_h_m.filter((value) => typeof value === "number" && Number.isFinite(value)).join(","),
  ].join("|");
}
