import maplibregl, { type GeoJSONSource } from "maplibre-gl";
import type { Feature, LineString } from "geojson";
import { buildEsriSatelliteStyle } from "./basemap.js";
import {
  clampDistanceRangeToFullRange,
  computeVisibleDistanceRangeFromScreen,
  getSegmentDistanceRange,
} from "./mapSync.js";
import { boundsForCoordinates } from "./mapTrack.js";
import type { DistanceRange, MapSyncView, ScreenSample } from "./mapSync.js";
import type { SegmentPayload } from "./types.js";

export interface LabelerMap {
  setSegment(payload: SegmentPayload, options?: SegmentMapOptions): void;
  syncToSegmentRange(syncView: MapSyncView, animated: boolean): void;
  getVisibleSegmentRange(payload: SegmentPayload): DistanceRange | null;
  onCameraChange(handler: () => void): () => void;
  getCameraState(): MapCameraState;
  restoreCameraState(camera: MapCameraState, animated: boolean): void;
  destroy(): void;
}

export interface SegmentMapOptions {
  fit?: boolean;
}

export interface MapCameraState {
  center: [number, number];
  zoom: number;
  bearing: number;
  pitch: number;
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
  let latestShouldFitSegment = true;

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
      renderPayload(map, latestPayload, latestShouldFitSegment);
      completedRenderVersion = latestRenderVersion;
    });
  };

  map.on("load", scheduleRender);
  map.on("idle", scheduleRender);

  function projectSegmentSamples(payload: SegmentPayload): ScreenSample[] {
    const samples: ScreenSample[] = [];
    const count = Math.min(payload.context.x_atc_m.length, payload.context.lon.length, payload.context.lat.length);
    for (let index = 0; index < count; index += 1) {
      const distanceKm = payload.context.x_atc_m[index] / 1000;
      const lon = payload.context.lon[index];
      const lat = payload.context.lat[index];
      if (!Number.isFinite(distanceKm) || !Number.isFinite(lon) || !Number.isFinite(lat)) {
        continue;
      }
      const point = map.project([lon, lat]);
      samples.push({ distanceKm, x: point.x, y: point.y });
    }
    return samples;
  }

  function getViewport() {
    const mapElement = map.getContainer();
    return {
      left: 0,
      top: 0,
      right: mapElement.clientWidth,
      bottom: mapElement.clientHeight,
    };
  }

  return {
    setSegment(payload: SegmentPayload, options: SegmentMapOptions = {}) {
      latestPayload = payload;
      latestShouldFitSegment = options.fit !== false;
      latestRenderVersion += 1;
      scheduleRender();
    },
    syncToSegmentRange(syncView: MapSyncView, animated: boolean) {
      const camera = map._cameraForBoxAndBearing(syncView.start, syncView.end, syncView.bearing, {
        padding: { top: 56, right: 80, bottom: 56, left: 80 },
      });
      const cameraOptions = {
        center: camera?.center ?? syncView.center,
        bearing: camera?.bearing ?? syncView.bearing,
        zoom: camera?.zoom,
        pitch: 0,
      };

      if (animated) {
        map.easeTo({ ...cameraOptions, duration: 700, essential: true });
      } else {
        map.jumpTo(cameraOptions);
      }
    },
    getVisibleSegmentRange(payload: SegmentPayload) {
      const visibleRange = computeVisibleDistanceRangeFromScreen(projectSegmentSamples(payload), getViewport());
      const fullRange = getSegmentDistanceRange(payload);
      return visibleRange && fullRange ? clampDistanceRangeToFullRange(visibleRange, fullRange) : null;
    },
    onCameraChange(handler: () => void) {
      map.on("moveend", handler);
      return () => {
        map.off("moveend", handler);
      };
    },
    getCameraState() {
      const center = map.getCenter();
      return {
        center: [center.lng, center.lat],
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
      };
    },
    restoreCameraState(camera: MapCameraState, animated: boolean) {
      const cameraOptions = {
        center: camera.center,
        zoom: camera.zoom,
        bearing: camera.bearing,
        pitch: camera.pitch,
      };
      if (animated) {
        map.easeTo({ ...cameraOptions, duration: 500, essential: true });
      } else {
        map.jumpTo(cameraOptions);
      }
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

function renderPayload(map: maplibregl.Map, payload: SegmentPayload, fitSegment: boolean): void {
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
  const bounds = fitSegment ? boundsForCoordinates(coordinates) : null;
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
