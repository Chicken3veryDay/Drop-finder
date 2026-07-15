import { createHash } from "node:crypto";
import { readdir, readFile, stat } from "node:fs/promises";
import { relative, resolve } from "node:path";

export const publicationRootFrom = (projectRoot) => resolve(projectRoot, "../cloud_pages");

const walkFiles = async (root, current = root) => {
  const entries = await readdir(current, { withFileTypes: true });
  const files = [];
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    const path = resolve(current, entry.name);
    if (entry.isDirectory()) files.push(...await walkFiles(root, path));
    else if (entry.isFile()) files.push(relative(root, path).replaceAll("\\", "/"));
  }
  return files;
};

export const sha256File = async (path) => createHash("sha256").update(await readFile(path)).digest("hex");

export const snapshotPublicationFiles = async (publicationRoot, relativePaths) => {
  const snapshot = new Map();
  for (const relativePath of relativePaths) {
    const absolutePath = resolve(publicationRoot, relativePath);
    const details = await stat(absolutePath);
    const files = details.isDirectory() ? await walkFiles(publicationRoot, absolutePath) : [relativePath];
    for (const file of files) snapshot.set(file, await sha256File(resolve(publicationRoot, file)));
  }
  return snapshot;
};

export const compareSnapshots = (before, after) => {
  const differences = [];
  const paths = new Set([...before.keys(), ...after.keys()]);
  for (const path of [...paths].sort()) {
    if (!before.has(path)) differences.push(`${path} was added`);
    else if (!after.has(path)) differences.push(`${path} was deleted`);
    else if (before.get(path) !== after.get(path)) differences.push(`${path} was modified`);
  }
  return differences;
};

export const listPublicationFiles = (publicationRoot) => walkFiles(publicationRoot);
