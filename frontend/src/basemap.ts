import type { StyleSpecification } from "maplibre-gl";

export const ESRI_WORLD_IMAGERY_TILE_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

export function buildEsriSatelliteStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      esriWorldImagery: {
        type: "raster",
        tiles: [ESRI_WORLD_IMAGERY_TILE_URL],
        tileSize: 256,
        attribution: "Esri, Maxar, Earthstar Geographics, and the GIS User Community",
      },
    },
    layers: [{ id: "esri-world-imagery", type: "raster", source: "esriWorldImagery" }],
  };
}
