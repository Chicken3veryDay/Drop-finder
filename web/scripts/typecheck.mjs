import { readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

async function walk(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...await walk(path));
    else if (/\.(?:m?js)$/.test(entry.name)) out.push(path);
  }
  return out;
}

const roots = ['src', 'scripts', 'test', 'tests'];
let count = 0;
for (const root of roots) {
  for (const file of await walk(new URL(`../${root}/`, import.meta.url).pathname)) {
    const result = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
    if (result.status !== 0) {
      process.stderr.write(result.stderr);
      process.exit(result.status ?? 1);
    }
    count += 1;
  }
}
console.log(`Parsed ${count} JavaScript modules without syntax errors.`);
