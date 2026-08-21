import type { LngLatBoundsLike } from "maplibre-gl";

export function boundsForCoordinates(coordinates: number[][]): LngLatBoundsLike | null {
  const unwrapped = unwrapTrackCoordinates(coordinates);
  if (unwrapped.length === 0) {
    return null;
  }
  let minLon = unwrapped[0][0];
  let maxLon = unwrapped[0][0];
  let minLat = unwrapped[0][1];
  let maxLat = unwrapped[0][1];
  for (const [lon, lat] of unwrapped) {
    minLon = Math.min(minLon, lon);
    maxLon = Math.max(maxLon, lon);
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
  }
  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ];
}

export function unwrapTrackCoordinates(coordinates: number[][]): number[][] {
  const unwrapped: number[][] = [];
  let previousLon: number | null = null;
  for (const coordinate of coordinates) {
    const lon = Number(coordinate[0]);
    const lat = Number(coordinate[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      continue;
    }
    const nextLon = unwrapLongitude(lon, previousLon);
    unwrapped.push([nextLon, lat]);
    previousLon = nextLon;
  }
  return unwrapped;
}

export function unwrapLongitude(lon: number, referenceLon: number | null): number {
  if (referenceLon === null) {
    return lon;
  }
  let unwrapped = lon;
  while (unwrapped - referenceLon > 180) {
    unwrapped -= 360;
  }
  while (unwrapped - referenceLon < -180) {
    unwrapped += 360;
  }
  return unwrapped;
}
