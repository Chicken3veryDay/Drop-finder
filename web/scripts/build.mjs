import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import { compareSnapshots, publicationRootFrom, snapshotPublicationFiles } from "./publication-utils.mjs";
import { verifyPublication } from "./verify-publication.mjs";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const publicationRoot = publicationRootFrom(projectRoot);
const protectedPaths = ["data", "manifest.webmanifest", "icon.svg", "sw.js"];

const before = await snapshotPublicationFiles(publicationRoot, protectedPaths);
await build({ configFile: resolve(projectRoot, "vite.config.ts") });
const after = await snapshotPublicationFiles(publicationRoot, protectedPaths);
const differences = compareSnapshots(before, after);
if (differences.length > 0) {
  throw new Error(`Frontend build changed protected publication files:\n${differences.join("\n")}`);
}
const result = await verifyPublication(publicationRoot);
console.log(`Built DropFinder frontend without altering ${before.size} protected files; verified ${result.assets} hashed assets.`);
