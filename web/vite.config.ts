import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const isE2eServer = process.env.DROPFINDER_E2E === "1";

export default defineConfig({
  base: "./",
  plugins: [react()],
  publicDir: isE2eServer ? "public" : false,
  ...(isE2eServer ? { server: { hmr: false } } : {}),
  optimizeDeps: {
    include: [
      "react",
      "react/jsx-runtime",
      "react-dom",
      "react-dom/client",
      "pdfjs-dist/legacy/build/pdf.mjs",
    ],
    ...(isE2eServer ? { noDiscovery: true } : {}),
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "../cloud_pages",
    emptyOutDir: false,
    assetsDir: "assets",
    sourcemap: false,
    manifest: "assets/vite-manifest.json",
    rollupOptions: {
      output: {
        entryFileNames: "assets/app-[hash].js",
        chunkFileNames: "assets/chunk-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: "./src/test/setup.ts",
    css: true,
    coverage: {
      reporter: ["text", "json-summary"],
    },
  },
});
