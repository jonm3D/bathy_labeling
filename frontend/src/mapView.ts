import maplibregl, { type GeoJSONSource } from "maplibre-gl";
import type { Feature, LineString } from "geojson";
import { buildEsriSatelliteStyle } from "./basemap.js";
import { boundsForCoordinates } from "./mapTrack.js";
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

  let latestPayload: SegmentPayload | null = null;
  let renderQueued = false;
  let latestRenderVersion = 0;
  let completedRenderVersion = 0;

  const scheduleRender = () => {
    if (renderQueued) {
      return;
    }
    renderQueued = true;
    requestAnimationFrame(() => {
      renderQueued = false;
      if (!latestPayload || !map.loaded() || latestRenderVersion === completedRenderVersion) {
        return;
      }
      map.resize();
      ensureLayers(map);
      renderPayload(map, latestPayload);
      completedRenderVersion = latestRenderVersion;
    });
  };

  map.on("load", scheduleRender);
  map.on("idle", scheduleRender);

  return {
    setSegment(payload: SegmentPayload) {
      latestPayload = payload;
      latestRenderVersion += 1;
      scheduleRender();
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
  const bounds = boundsForCoordinates(coordinates);
  if (bounds) {
    map.fitBounds(bounds, { padding: 36, duration: 350 });
  }
}

function emptyLine(): Feature<LineString> {
  return {
    type: "Feature",
    properties: {},
    geometry: { type: "LineString", coordinates: [] },
  };
}
