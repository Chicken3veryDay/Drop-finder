import { copyFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = resolve(webRoot, 'node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs');
const destination = resolve(webRoot, 'public/pdfjs/pdf.worker.min.mjs');

await mkdir(dirname(destination), { recursive: true });
await copyFile(source, destination);
console.log(`Prepared raw PDF.js worker at ${destination}`);
