import { cp, mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(fileURLToPath(new URL("../../", import.meta.url)));
const repoRoot = resolve(webRoot, "..");
const source = resolve(repoRoot, "cloud_pages/data/catalog-v4");
const publicRoot = resolve(webRoot, "public");
const target = resolve(publicRoot, "data/catalog-v4");

await mkdir(resolve(publicRoot, "data"), { recursive: true });
await rm(target, { recursive: true, force: true });
await cp(source, target, { recursive: true, force: true });
console.log(`copied catalog-v4 browser fixture to ${target}`);
