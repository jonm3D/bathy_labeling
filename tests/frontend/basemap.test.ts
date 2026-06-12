import assert from "node:assert/strict";
import test from "node:test";

import { ESRI_WORLD_IMAGERY_TILE_URL, buildEsriSatelliteStyle } from "../../frontend/src/basemap.js";

interface RasterSourceLike {
  type: string;
  tiles?: string[];
}

test("satellite basemap uses Esri World Imagery tiles", () => {
  const style = buildEsriSatelliteStyle();
  const source = style.sources.esriWorldImagery as RasterSourceLike;

  assert.equal(ESRI_WORLD_IMAGERY_TILE_URL, "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}");
  assert.equal(source.type, "raster");
  assert.deepEqual(source.tiles, [ESRI_WORLD_IMAGERY_TILE_URL]);
  assert.equal(style.layers[0].id, "esri-world-imagery");
});
