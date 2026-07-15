import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  base: './',
  optimizeDeps: {
    include: [
      'pdfjs-dist/legacy/build/pdf.mjs',
      'pdfjs-dist/legacy/build/pdf.worker.min.mjs',
    ],
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
