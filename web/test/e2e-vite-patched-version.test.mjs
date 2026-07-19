import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const MINIMUM_PATCHED_VITE_6 = [6, 4, 2];

function numericVersion(value) {
  const match = String(value ?? '').match(/^(\d+)\.(\d+)\.(\d+)$/);
  assert.ok(match, `Vite must be pinned to an exact stable version, received ${value}`);
  return match.slice(1).map(Number);
}

function atLeast(left, right) {
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference !== 0) return difference > 0;
  }
  return true;
}

test('managed E2E Vite dependency is pinned to a patched release', async () => {
  const packageJson = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  const lockfile = JSON.parse(await readFile(new URL('../package-lock.json', import.meta.url), 'utf8'));
  const declared = packageJson.devDependencies?.vite;
  const lockedRoot = lockfile.packages?.['']?.devDependencies?.vite;
  const resolved = lockfile.packages?.['node_modules/vite']?.version;

  assert.equal(declared, lockedRoot, 'package.json and package-lock root Vite pins must agree');
  assert.equal(declared, resolved, 'declared and resolved Vite versions must agree');
  const version = numericVersion(resolved);
  assert.ok(
    version[0] > 6 || (version[0] === 6 && atLeast(version, MINIMUM_PATCHED_VITE_6)),
    `Vite ${resolved} is below the patched 6.x floor 6.4.2`,
  );
});
