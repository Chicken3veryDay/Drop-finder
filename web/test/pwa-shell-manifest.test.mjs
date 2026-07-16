import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import {
  buildShellManifest,
  collectStaticViteAssets,
  selectStartupWorkerAssets,
} from '../scripts/pwa/generate-shell-manifest.mjs';

test('static Vite asset traversal excludes dynamic document entries', () => {
  const manifest = {
    'index.html': {
      file: 'assets/app-HASH_123.js',
      isEntry: true,
      imports: ['src/static.ts'],
      dynamicImports: ['pdf.mjs'],
      css: ['assets/index-HASH_123.css'],
    },
    'src/static.ts': {
      file: 'assets/chunk-STATIC_1.js',
      assets: ['assets/logo-ASSET_12.svg'],
    },
    'pdf.mjs': {
      file: 'assets/chunk-PDFJS_12.js',
      isDynamicEntry: true,
      assets: ['assets/pdf.worker-PDFJS_12.mjs'],
    },
  };
  assert.deepEqual(collectStaticViteAssets(manifest), [
    'assets/app-HASH_123.js',
    'assets/chunk-STATIC_1.js',
    'assets/index-HASH_123.css',
    'assets/logo-ASSET_12.svg',
  ]);
});

test('startup worker selection follows the current entry reference and ignores stale output', () => {
  const current = 'marketplace-query-worker-CNdCK8BC.js';
  const stale = 'marketplace-query-worker-AAAAAAAA.js';
  assert.deepEqual(
    selectStartupWorkerAssets([current, stale], [`new Worker(new URL("./${current}", import.meta.url))`]),
    [`assets/${current}`],
  );
  assert.throws(
    () => selectStartupWorkerAssets([current], ['const noWorkerReference = true;']),
    /found 0/,
  );
  assert.throws(
    () => selectStartupWorkerAssets([current, stale], [`"${current}"; "${stale}";`]),
    /found 2/,
  );
  assert.throws(
    () => selectStartupWorkerAssets([], [`"${current}";`]),
    /output is missing/,
  );
});

test('shell manifest contains startup assets without eager PDF.js chunks', async t => {
  const root = await mkdtemp(resolve(tmpdir(), 'dropfinder-shell-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const assets = resolve(root, 'assets');
  const worker = 'marketplace-query-worker-CNdCK8BC.js';
  const appSource = `new Worker(new URL("./${worker}", import.meta.url));`;
  await mkdir(assets);
  await Promise.all([
    writeFile(resolve(root, 'index.html'), 'index'),
    writeFile(resolve(root, 'manifest.webmanifest'), 'manifest'),
    writeFile(resolve(root, 'icon.svg'), 'icon'),
    writeFile(resolve(assets, 'app-D1_HGx2j.js'), appSource),
    writeFile(resolve(assets, 'index-UDKaS5UJ.css'), 'css'),
    writeFile(resolve(assets, worker), 'worker'),
    writeFile(resolve(assets, 'marketplace-query-worker-AAAAAAAA.js'), 'stale-worker'),
    writeFile(resolve(assets, 'chunk-CgeV8iME.js'), 'pdf'),
    writeFile(resolve(assets, 'chunk-D6fhxGoq.js'), 'pdf-url'),
    writeFile(resolve(assets, 'pdf.worker.min-Cr_QfRGn.mjs'), 'pdf-worker'),
  ]);
  await writeFile(resolve(assets, 'vite-manifest.json'), JSON.stringify({
    'index.html': {
      file: 'assets/app-D1_HGx2j.js',
      isEntry: true,
      dynamicImports: ['pdf.mjs', 'pdf.worker.mjs?url'],
      css: ['assets/index-UDKaS5UJ.css'],
    },
    'pdf.mjs': { file: 'assets/chunk-CgeV8iME.js', isDynamicEntry: true },
    'pdf.worker.mjs?url': {
      file: 'assets/chunk-D6fhxGoq.js',
      isDynamicEntry: true,
      assets: ['assets/pdf.worker.min-Cr_QfRGn.mjs'],
    },
  }));

  const manifest = await buildShellManifest(root);
  assert.deepEqual(manifest.assets, [
    './',
    './assets/app-D1_HGx2j.js',
    './assets/index-UDKaS5UJ.css',
    `./assets/${worker}`,
    './icon.svg',
    './index.html',
    './manifest.webmanifest',
  ]);
  const expectedBytes = Buffer.byteLength(appSource) + 3 + 6 + 4 + 5 + 8;
  assert.equal(manifest.records.reduce((sum, record) => sum + record.bytes, 0), expectedBytes);
  assert.equal(manifest.assets.some(path => /pdf|chunk-Cge|chunk-D6f|AAAAAAAA/.test(path)), false);
  await assert.doesNotReject(() => readFile(resolve(assets, 'chunk-CgeV8iME.js')));
});
