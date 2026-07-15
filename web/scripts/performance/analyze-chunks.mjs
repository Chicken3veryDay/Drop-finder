import { readFile, readdir, stat } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(new URL('../../', import.meta.url).pathname);
const dist = resolve(root, 'dist-platform');
const manifest = JSON.parse(await readFile(resolve(dist, '.vite/manifest.json'), 'utf8'));
const entries = Object.values(manifest).filter(item => item.isEntry);
const dynamic = Object.values(manifest).filter(item => item.isDynamicEntry);
if (entries.length !== 1) throw new Error(`Expected one platform entry, found ${entries.length}`);
const entry = entries[0];
const entryPath = resolve(dist, entry.file);
const entryBytes = (await stat(entryPath)).size;
const entryText = await readFile(entryPath, 'utf8');
if (entryBytes > 180 * 1024) throw new Error(`Initial platform chunk is ${entryBytes} bytes; budget is 184320`);
if (/class PDFWorker|pdfjsVersion|Cannot polyfill `DOMMatrix`/.test(entryText)) {
  throw new Error('PDF.js implementation leaked into the initial platform chunk');
}
const files = await readdir(resolve(dist, 'assets'));
const pdfChunks = [];
for (const file of files) {
  if (!file.endsWith('.js')) continue;
  const text = await readFile(resolve(dist, 'assets', file), 'utf8');
  if (/PDFWorker|getDocument|pdfjsVersion|pdfjs-dist/.test(text)) pdfChunks.push(file);
}
if (!pdfChunks.length || !dynamic.length) throw new Error('No lazy PDF.js dynamic chunk was emitted');
console.log(JSON.stringify({ entry: entry.file, entryBytes, dynamicChunks: dynamic.map(item => item.file), pdfChunks }, null, 2));
