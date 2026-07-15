import { defineConfig } from "vite";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  base: "./",
  optimizeDeps: {
    include: ["pdfjs-dist/legacy/build/pdf.mjs"],
  },
  build: {
    outDir: "dist-platform",
    emptyOutDir: true,
    manifest: true,
    sourcemap: true,
    lib: {
      entry: resolve(root, "src/platform/index.js"),
      formats: ["es"],
      fileName: "dropfinder-platform",
    },
    rollupOptions: {
      output: {
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
