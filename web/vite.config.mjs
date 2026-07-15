import { defineConfig } from 'vite';
import { resolve } from 'node:path';

const isE2eServer = process.env.DROPFINDER_E2E === '1';

export default defineConfig({
  base: './',
  ...(isE2eServer ? { server: { hmr: false } } : {}),
  optimizeDeps: {
    include: ['pdfjs-dist/legacy/build/pdf.mjs'],
    ...(isE2eServer ? { noDiscovery: true } : {}),
  },
  build: {
    outDir: 'dist-platform',
    emptyOutDir: true,
    manifest: true,
    sourcemap: true,
    lib: {
      entry: resolve(import.meta.dirname, 'src/platform/index.js'),
      formats: ['es'],
      fileName: 'dropfinder-platform',
    },
    rollupOptions: {
      output: {
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
});
