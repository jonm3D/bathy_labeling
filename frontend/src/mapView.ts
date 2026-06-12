import maplibregl, { type GeoJSONSource, type LngLatBoundsLike } from "maplibre-gl";
import type { Feature, LineString } from "geojson";
import { buildEsriSatelliteStyle } from "./basemap.js";
import type { SegmentPayload } from "./types.js";

export interface LabelerMap {
  setSegment(payload: SegmentPayload): void;
  destroy(): void;
}

export function createMap(container: HTMLElement): LabelerMap {
  const map = new maplibregl.Map({
    container,
    style: buildEsriSatelliteStyle(),
    center: [0, 0],
    zoom: 2,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");

  let pendingPayload: SegmentPayload | null = null;
  map.on("load", () => {
    ensureLayers(map);
    if (pendingPayload) {
      renderPayload(map, pendingPayload);
      pendingPayload = null;
    }
  });

  return {
    setSegment(payload: SegmentPayload) {
      if (!map.loaded()) {
        pendingPayload = payload;
        return;
      }
      ensureLayers(map);
      renderPayload(map, payload);
    },
    destroy() {
      map.remove();
    },
  };
}

function ensureLayers(map: maplibregl.Map): void {
  if (!map.getSource("segment-track")) {
    map.addSource("segment-track", {
      type: "geojson",
      data: emptyLine(),
    });
    map.addLayer({
      id: "segment-track-outline",
      type: "line",
      source: "segment-track",
      paint: { "line-color": "#0f172a", "line-width": 5, "line-opacity": 0.65 },
    });
    map.addLayer({
      id: "segment-track",
      type: "line",
      source: "segment-track",
      paint: { "line-color": "#2a9d8f", "line-width": 2.5, "line-opacity": 0.95 },
    });
  }
}

function renderPayload(map: maplibregl.Map, payload: SegmentPayload): void {
  const coordinates = payload.context.lon.map((lon, index) => [lon, payload.context.lat[index]]);
  const source = map.getSource("segment-track") as GeoJSONSource | undefined;
  source?.setData({
    type: "Feature",
    properties: {},
    geometry: {
      type: "LineString",
      coordinates,
    },
  });
  const bounds = boundsFor(coordinates);
  if (bounds) {
    map.fitBounds(bounds, { padding: 36, duration: 350 });
  }
}

function boundsFor(coordinates: number[][]): LngLatBoundsLike | null {
  if (coordinates.length === 0) {
    return null;
  }
  let minLon = coordinates[0][0];
  let maxLon = coordinates[0][0];
  let minLat = coordinates[0][1];
  let maxLat = coordinates[0][1];
  for (const [lon, lat] of coordinates) {
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

function emptyLine(): Feature<LineString> {
  return {
    type: "Feature",
    properties: {},
    geometry: { type: "LineString", coordinates: [] },
  };
}
