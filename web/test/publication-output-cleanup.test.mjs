import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  compareSnapshots,
  removeGeneratedPublicationFiles,
  snapshotPublicationFiles,
} from "../scripts/publication-utils.mjs";

const protectedPaths = ["data", "manifest.webmanifest", "icon.svg", "sw.js"];

const assertMissing = async (path) => {
  await assert.rejects(access(path), (error) => error?.code === "ENOENT");
};

test("generated output cleanup removes stale Vite files and preserves publication state", async () => {
  const publicationRoot = await mkdtemp(join(tmpdir(), "dropfinder-publication-cleanup-"));
  try {
    await mkdir(join(publicationRoot, "assets", "nested"), { recursive: true });
    await mkdir(join(publicationRoot, "data"), { recursive: true });
    await writeFile(join(publicationRoot, "assets", "app-OLDHASH.js"), "old app");
    await writeFile(join(publicationRoot, "assets", "nested", "chunk-OLDHASH.js"), "old chunk");
    await writeFile(join(publicationRoot, "index.html"), "old index");
    await writeFile(join(publicationRoot, "data", "catalog.json"), '{"products":[]}\n');
    await writeFile(join(publicationRoot, "manifest.webmanifest"), "manifest");
    await writeFile(join(publicationRoot, "icon.svg"), "<svg />");
    await writeFile(join(publicationRoot, "sw.js"), "service worker");

    const before = await snapshotPublicationFiles(publicationRoot, protectedPaths);
    await removeGeneratedPublicationFiles(publicationRoot);
    await removeGeneratedPublicationFiles(publicationRoot);
    const after = await snapshotPublicationFiles(publicationRoot, protectedPaths);

    assert.deepEqual(compareSnapshots(before, after), []);
    await assertMissing(join(publicationRoot, "assets"));
    await assertMissing(join(publicationRoot, "index.html"));
    assert.equal(await readFile(join(publicationRoot, "data", "catalog.json"), "utf8"), '{"products":[]}\n');
  } finally {
    await rm(publicationRoot, { force: true, recursive: true });
  }
});
