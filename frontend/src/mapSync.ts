import type { SegmentPayload } from "./types.js";

export type DistanceRange = [number, number];
export type LngLatTuple = [number, number];

export interface MapSyncView {
  rangeKm: DistanceRange;
  start: LngLatTuple;
  end: LngLatTuple;
  center: LngLatTuple;
  bearing: number;
}

export interface ScreenSample {
  distanceKm: number;
  x: number;
  y: number;
}

export interface ScreenViewport {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface SyncSample {
  distanceKm: number;
  lon: number;
  lat: number;
}

const MIN_RANGE_FRACTION = 0.01;
const MIN_RANGE_KM = 0.001;
const MAX_MERCATOR_LAT = 85.05112878;

export function getSegmentDistanceRange(payload: SegmentPayload): DistanceRange | null {
  const distances = payload.context.x_atc_m.map((value) => value / 1000).filter(Number.isFinite);
  if (distances.length < 2) {
    return null;
  }

  const min = Math.min(...distances);
  const max = Math.max(...distances);
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return null;
  }
  return [min, max];
}

export function computeMapSyncView(
  payload: SegmentPayload,
  requestedRange: DistanceRange | null,
): MapSyncView | null {
  const samples = buildSamples(payload);
  const fullRange = getSegmentDistanceRange(payload);
  if (samples.length < 2 || fullRange === null) {
    return null;
  }

  const rangeKm = clampDistanceRangeToFullRange(requestedRange ?? fullRange, fullRange);
  const start = interpolateAtDistance(samples, rangeKm[0]);
  const end = interpolateAtDistance(samples, rangeKm[1]);
  if (!start || !end || (start[0] === end[0] && start[1] === end[1])) {
    return null;
  }

  return {
    rangeKm,
    start,
    end,
    center: [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2],
    bearing: computeHorizontalBearing(start, end),
  };
}

export function clampDistanceRangeToFullRange(requestedRange: DistanceRange, fullRange: DistanceRange): DistanceRange {
  return normalizeRange(requestedRange, fullRange);
}

export function extractPlotlyXRange(
  update: Record<string, unknown>,
  fallbackRange: DistanceRange | null,
): DistanceRange | null {
  if (update["xaxis.autorange"] === true) {
    return fallbackRange;
  }

  const rangeArray = update["xaxis.range"];
  if (Array.isArray(rangeArray) && rangeArray.length >= 2) {
    return toNumericRange(rangeArray[0], rangeArray[1]);
  }

  if ("xaxis.range[0]" in update && "xaxis.range[1]" in update) {
    return toNumericRange(update["xaxis.range[0]"], update["xaxis.range[1]"]);
  }

  return null;
}

export function computeVisibleDistanceRangeFromScreen(
  samples: ScreenSample[],
  viewport: ScreenViewport,
): DistanceRange | null {
  const sortedSamples = samples
    .filter(
      (sample) =>
        Number.isFinite(sample.distanceKm) &&
        Number.isFinite(sample.x) &&
        Number.isFinite(sample.y),
    )
    .sort((a, b) => a.distanceKm - b.distanceKm);
  if (sortedSamples.length < 2) {
    return null;
  }

  const visibleDistances: number[] = [];
  for (const sample of sortedSamples) {
    if (isPointInViewport(sample, viewport)) {
      visibleDistances.push(sample.distanceKm);
    }
  }

  for (let index = 1; index < sortedSamples.length; index += 1) {
    const start = sortedSamples[index - 1];
    const end = sortedSamples[index];
    const clipped = clipSegmentToViewport(start, end, viewport);
    if (clipped) {
      visibleDistances.push(
        interpolateDistance(start.distanceKm, end.distanceKm, clipped[0]),
        interpolateDistance(start.distanceKm, end.distanceKm, clipped[1]),
      );
    }
  }

  addEndpointRayDistances(sortedSamples[0], sortedSamples[1], viewport, visibleDistances);
  addEndpointRayDistances(
    sortedSamples[sortedSamples.length - 1],
    sortedSamples[sortedSamples.length - 2],
    viewport,
    visibleDistances,
  );

  if (visibleDistances.length === 0) {
    return null;
  }

  return [Math.min(...visibleDistances), Math.max(...visibleDistances)];
}

function buildSamples(payload: SegmentPayload): SyncSample[] {
  const samples: SyncSample[] = [];
  const count = Math.min(payload.context.x_atc_m.length, payload.context.lon.length, payload.context.lat.length);
  for (let index = 0; index < count; index += 1) {
    const distanceKm = payload.context.x_atc_m[index] / 1000;
    const lon = payload.context.lon[index];
    const lat = payload.context.lat[index];
    if (Number.isFinite(distanceKm) && Number.isFinite(lon) && Number.isFinite(lat)) {
      samples.push({ distanceKm, lon, lat });
    }
  }
  return samples.sort((a, b) => a.distanceKm - b.distanceKm);
}

function normalizeRange(requestedRange: DistanceRange, fullRange: DistanceRange): DistanceRange {
  const sorted: DistanceRange =
    requestedRange[0] <= requestedRange[1] ? [requestedRange[0], requestedRange[1]] : [requestedRange[1], requestedRange[0]];
  let min = clamp(sorted[0], fullRange[0], fullRange[1]);
  let max = clamp(sorted[1], fullRange[0], fullRange[1]);

  const fullSpan = fullRange[1] - fullRange[0];
  const minSpan = Math.min(fullSpan, Math.max(MIN_RANGE_KM, fullSpan * MIN_RANGE_FRACTION));
  if (max - min < minSpan) {
    const midpoint = (min + max) / 2;
    min = midpoint - minSpan / 2;
    max = midpoint + minSpan / 2;
    if (min < fullRange[0]) {
      max = Math.min(fullRange[1], max + (fullRange[0] - min));
      min = fullRange[0];
    }
    if (max > fullRange[1]) {
      min = Math.max(fullRange[0], min - (max - fullRange[1]));
      max = fullRange[1];
    }
  }

  return [min, max];
}

function interpolateAtDistance(samples: SyncSample[], distanceKm: number): LngLatTuple | null {
  if (distanceKm <= samples[0].distanceKm) {
    return interpolateBetweenSamples(samples[0], samples[1], distanceKm);
  }

  const last = samples[samples.length - 1];
  if (distanceKm >= last.distanceKm) {
    return interpolateBetweenSamples(samples[samples.length - 2], last, distanceKm);
  }

  for (let index = 1; index < samples.length; index += 1) {
    const previous = samples[index - 1];
    const next = samples[index];
    if (distanceKm > next.distanceKm) {
      continue;
    }
    return interpolateBetweenSamples(previous, next, distanceKm);
  }

  return null;
}

function interpolateBetweenSamples(start: SyncSample, end: SyncSample, distanceKm: number): LngLatTuple | null {
  const span = end.distanceKm - start.distanceKm;
  if (span === 0) {
    return [end.lon, end.lat];
  }
  const fraction = (distanceKm - start.distanceKm) / span;
  return [start.lon + (end.lon - start.lon) * fraction, start.lat + (end.lat - start.lat) * fraction];
}

function computeHorizontalBearing(start: LngLatTuple, end: LngLatTuple): number {
  const startProjected = projectMercator(start);
  const endProjected = projectMercator(end);
  const dx = endProjected[0] - startProjected[0];
  const dy = endProjected[1] - startProjected[1];
  const azimuth = radiansToDegrees(Math.atan2(dx, dy));
  return normalizeBearing(azimuth - 90);
}

function projectMercator([lon, lat]: LngLatTuple): [number, number] {
  const clampedLat = clamp(lat, -MAX_MERCATOR_LAT, MAX_MERCATOR_LAT);
  const latRadians = degreesToRadians(clampedLat);
  return [degreesToRadians(lon), Math.log(Math.tan(Math.PI / 4 + latRadians / 2))];
}

function toNumericRange(start: unknown, end: unknown): DistanceRange | null {
  const parsedStart = typeof start === "number" ? start : Number.parseFloat(String(start));
  const parsedEnd = typeof end === "number" ? end : Number.parseFloat(String(end));
  if (!Number.isFinite(parsedStart) || !Number.isFinite(parsedEnd)) {
    return null;
  }
  return [parsedStart, parsedEnd];
}

function isPointInViewport(sample: ScreenSample, viewport: ScreenViewport): boolean {
  return sample.x >= viewport.left && sample.x <= viewport.right && sample.y >= viewport.top && sample.y <= viewport.bottom;
}

function clipSegmentToViewport(
  start: ScreenSample,
  end: ScreenSample,
  viewport: ScreenViewport,
): [number, number] | null {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const clipped = clipParametricLineToViewport(start, dx, dy, viewport);
  if (clipped === null) {
    return null;
  }
  const t0 = Math.max(0, clipped[0]);
  const t1 = Math.min(1, clipped[1]);
  return t0 <= t1 ? [t0, t1] : null;
}

function addEndpointRayDistances(
  endpoint: ScreenSample,
  adjacent: ScreenSample,
  viewport: ScreenViewport,
  output: number[],
): void {
  const dx = endpoint.x - adjacent.x;
  const dy = endpoint.y - adjacent.y;
  const distanceDelta = endpoint.distanceKm - adjacent.distanceKm;
  const clipped = clipParametricLineToViewport(endpoint, dx, dy, viewport);
  if (clipped === null) {
    return;
  }

  const rayInterval: [number, number] = [Math.max(0, clipped[0]), clipped[1]];
  if (rayInterval[0] > rayInterval[1]) {
    return;
  }
  output.push(
    endpoint.distanceKm + distanceDelta * rayInterval[0],
    endpoint.distanceKm + distanceDelta * rayInterval[1],
  );
}

function clipParametricLineToViewport(
  start: Pick<ScreenSample, "x" | "y">,
  dx: number,
  dy: number,
  viewport: ScreenViewport,
): [number, number] | null {
  let t0 = Number.NEGATIVE_INFINITY;
  let t1 = Number.POSITIVE_INFINITY;

  const edges: Array<[number, number]> = [
    [-dx, start.x - viewport.left],
    [dx, viewport.right - start.x],
    [-dy, start.y - viewport.top],
    [dy, viewport.bottom - start.y],
  ];

  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) {
        return null;
      }
      continue;
    }

    const ratio = q / p;
    if (p < 0) {
      if (ratio > t1) {
        return null;
      }
      t0 = Math.max(t0, ratio);
    } else {
      if (ratio < t0) {
        return null;
      }
      t1 = Math.min(t1, ratio);
    }
  }

  return [t0, t1];
}

function interpolateDistance(startDistance: number, endDistance: number, fraction: number): number {
  return startDistance + (endDistance - startDistance) * fraction;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function degreesToRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function radiansToDegrees(radians: number): number {
  return (radians * 180) / Math.PI;
}

function normalizeBearing(bearing: number): number {
  let normalized = ((bearing + 180) % 360) - 180;
  if (normalized < -180) {
    normalized += 360;
  }
  return normalized;
}
