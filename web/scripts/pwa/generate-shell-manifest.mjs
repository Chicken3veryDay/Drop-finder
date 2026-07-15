import { readdir, readFile, writeFile } from 'node:fs/promises';
import { relative, resolve } from 'node:path';
import { createHash } from 'node:crypto';

const repoRoot = resolve(new URL('../../../', import.meta.url).pathname);
const publicRoot = resolve(repoRoot, 'cloud_pages');
const output = resolve(publicRoot, 'app-shell.json');
const required = ['index.html', 'manifest.webmanifest', 'icon.svg'];
const assetsDir = resolve(publicRoot, 'assets');

async function walk(dir) {
  try {
    const out = [];
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const path = resolve(dir, entry.name);
      if (entry.isDirectory()) out.push(...await walk(path));
      else if (/\.(?:js|css|woff2?|png|svg|webp)$/.test(entry.name)) out.push(path);
    }
    return out;
  } catch { return []; }
}

const paths = [...required.map(name => resolve(publicRoot, name)), ...await walk(assetsDir)];
const records = [];
for (const path of paths) {
  const bytes = await readFile(path);
  records.push({
    path: `./${relative(publicRoot, path).replaceAll('\\', '/')}`,
    bytes: bytes.byteLength,
    sha256: createHash('sha256').update(bytes).digest('hex'),
  });
}
records.sort((a, b) => a.path.localeCompare(b.path));
const version = createHash('sha256').update(JSON.stringify(records)).digest('hex').slice(0, 16);
const manifest = {
  schema_version: 'dropfinder-app-shell-v1',
  version,
  assets: ['./', ...records.map(record => record.path)],
  records,
};
const text = `${JSON.stringify(manifest, null, 2)}\n`;
if (process.argv.includes('--check')) {
  const existing = await readFile(output, 'utf8');
  if (existing !== text) {
    console.error('cloud_pages/app-shell.json is stale; run npm run pwa:manifest');
    process.exit(1);
  }
} else {
  await writeFile(output, text);
  console.log(`wrote ${relative(repoRoot, output)} (${records.length} immutable shell assets)`);
}
