import { readdir, readFile, writeFile } from 'node:fs/promises';
import { relative, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';

const repoRoot = resolve(fileURLToPath(new URL('../../../', import.meta.url)));
const publicRoot = resolve(repoRoot, 'cloud_pages');
const required = ['index.html', 'manifest.webmanifest', 'icon.svg'];
const startupWorkerDefinitions = [
  {
    label: 'marketplace query worker',
    filename: /^marketplace-query-worker-[A-Za-z0-9_-]{8,}\.js$/,
    reference: /marketplace-query-worker-[A-Za-z0-9_-]{8,}\.js/g,
  },
];

function generatedAssetPath(value, label) {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`Vite manifest ${label} must be a non-empty path`);
  }
  const normalized = value.replaceAll('\\', '/');
  if (!normalized.startsWith('assets/') || normalized.startsWith('/') || normalized.split('/').includes('..')) {
    throw new Error(`Vite manifest ${label} escapes the generated assets directory: ${value}`);
  }
  return normalized;
}

export function collectStaticViteAssets(manifest) {
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
    throw new Error('Vite manifest must be an object');
  }
  const entryKey = 'index.html';
  const entry = manifest[entryKey];
  if (!entry || typeof entry !== 'object' || entry.isEntry !== true) {
    throw new Error('Vite manifest has no index.html entry asset');
  }

  const assets = new Set();
  const visited = new Set();
  const visit = key => {
    if (visited.has(key)) return;
    visited.add(key);
    const record = manifest[key];
    if (!record || typeof record !== 'object') {
      throw new Error(`Vite manifest references missing static import: ${key}`);
    }
    if (!record.file) throw new Error(`Vite manifest static entry ${key} has no output file`);
    assets.add(generatedAssetPath(record.file, `${key}.file`));
    for (const [field, values] of [['css', record.css], ['assets', record.assets]]) {
      if (values === undefined) continue;
      if (!Array.isArray(values)) throw new Error(`Vite manifest ${key}.${field} must be an array`);
      for (const value of values) assets.add(generatedAssetPath(value, `${key}.${field}`));
    }
    if (record.imports !== undefined && !Array.isArray(record.imports)) {
      throw new Error(`Vite manifest ${key}.imports must be an array`);
    }
    for (const imported of record.imports ?? []) visit(imported);
  };
  visit(entryKey);
  return [...assets].sort();
}

export function selectStartupWorkerAssets(assetNames, staticJavaScript) {
  const available = new Set(assetNames);
  const selected = [];
  const source = staticJavaScript.join('\n');
  for (const definition of startupWorkerDefinitions) {
    const references = new Set(source.match(definition.reference) ?? []);
    if (references.size !== 1) {
      throw new Error(`Expected exactly one ${definition.label} reference in static entry assets, found ${references.size}`);
    }
    const [filename] = references;
    if (!definition.filename.test(filename) || !available.has(filename)) {
      throw new Error(`Referenced ${definition.label} output is missing: ${filename}`);
    }
    selected.push(`assets/${filename}`);
  }
  return selected;
}

export async function buildShellManifest(root = publicRoot) {
  const assetsDir = resolve(root, 'assets');
  const viteManifest = JSON.parse(await readFile(resolve(assetsDir, 'vite-manifest.json'), 'utf8'));
  const assetNames = (await readdir(assetsDir, { withFileTypes: true }))
    .filter(entry => entry.isFile())
    .map(entry => entry.name);
  const staticAssets = collectStaticViteAssets(viteManifest);
  const staticJavaScript = await Promise.all(staticAssets
    .filter(name => /\.(?:m?js)$/.test(name))
    .map(name => readFile(resolve(root, name), 'utf8')));
  const generatedAssets = new Set([
    ...staticAssets,
    ...selectStartupWorkerAssets(assetNames, staticJavaScript),
  ]);
  const paths = [
    ...required.map(name => resolve(root, name)),
    ...[...generatedAssets].sort().map(name => resolve(root, name)),
  ];
  const records = [];
  for (const path of paths) {
    const bytes = await readFile(path);
    records.push({
      path: `./${relative(root, path).replaceAll('\\', '/')}`,
      bytes: bytes.byteLength,
      sha256: createHash('sha256').update(bytes).digest('hex'),
    });
  }
  records.sort((a, b) => a.path.localeCompare(b.path));
  const version = createHash('sha256').update(JSON.stringify(records)).digest('hex').slice(0, 16);
  return {
    schema_version: 'dropfinder-app-shell-v1',
    version,
    assets: ['./', ...records.map(record => record.path)],
    records,
  };
}

export async function writeShellManifest({ root = publicRoot, check = false } = {}) {
  const output = resolve(root, 'app-shell.json');
  const manifest = await buildShellManifest(root);
  const text = `${JSON.stringify(manifest, null, 2)}\n`;
  if (check) {
    const existing = await readFile(output, 'utf8');
    if (existing !== text) {
      console.error('cloud_pages/app-shell.json is stale; run npm run pwa:manifest');
      return false;
    }
  } else {
    await writeFile(output, text);
    console.log(`wrote ${relative(repoRoot, output)} (${manifest.records.length} immutable shell assets)`);
  }
  return true;
}

const invokedPath = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : null;
if (invokedPath === import.meta.url) {
  const ok = await writeShellManifest({ check: process.argv.includes('--check') });
  if (!ok) process.exitCode = 1;
}
