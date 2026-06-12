import { defineConfig } from "vite";

export default defineConfig({
  cacheDir: ".vite-cache",
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
