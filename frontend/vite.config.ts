import { defineConfig } from "vite";

export default defineConfig({
  cacheDir: ".vite-cache",
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          map: ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/mapbox", "maplibre-gl"],
          plot: ["plotly.js-dist-min"],
        },
      },
    },
  },
});
