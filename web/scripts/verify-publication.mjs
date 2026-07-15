import { readFile, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { listPublicationFiles, publicationRootFrom } from "./publication-utils.mjs";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const requiredFiles = [
  "index.html",
  "manifest.webmanifest",
  "icon.svg",
  "sw.js",
  "data/catalog.json",
  "data/status.json",
  "data/runtime.json",
];

const assertFile = async (publicationRoot, relativePath) => {
  const details = await stat(resolve(publicationRoot, relativePath));
  if (!details.isFile() || details.size === 0) throw new Error(`Missing or empty publication file: ${relativePath}`);
};

export const verifyPublication = async (root = publicationRootFrom(projectRoot)) => {
  await Promise.all(requiredFiles.map((path) => assertFile(root, path)));

  const files = await listPublicationFiles(root);
  const builtAssets = files.filter((path) => path.startsWith("assets/") && !path.endsWith("vite-manifest.json"));
  if (builtAssets.length === 0) throw new Error("Production build emitted no hashed assets.");
  if (builtAssets.some((path) => !/-[A-Za-z0-9_-]{6,}\./.test(path))) {
    throw new Error(`Production assets must be content-hashed: ${builtAssets.join(", ")}`);
  }

  const index = await readFile(resolve(root, "index.html"), "utf8");
  if (!index.includes('href="./manifest.webmanifest"')) throw new Error("index.html must use a relative manifest path.");
  if (!index.includes('href="./icon.svg"')) throw new Error("index.html must use a relative icon path.");
  if (!index.includes("./assets/")) throw new Error("index.html must use relative hashed asset paths.");
  if (/\b(?:src|href)="\/(?!\/)/.test(index)) throw new Error("index.html contains a root-absolute asset path.");
  if (index.includes("src/app/main.tsx")) throw new Error("index.html still references the development entry point.");

  const manifest = JSON.parse(await readFile(resolve(root, "manifest.webmanifest"), "utf8"));
  if (manifest.start_url !== "./" || manifest.scope !== "./") throw new Error("PWA manifest must remain subpath-safe.");

  const serviceWorker = await readFile(resolve(root, "sw.js"), "utf8");
  for (const required of ["index.html", "manifest.webmanifest", "data/catalog.json", "data/status.json"]) {
    if (!serviceWorker.includes(required)) throw new Error(`Service worker does not preserve ${required}.`);
  }

  return { files: files.length, assets: builtAssets.length };
};

const invokedPath = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : "";
if (import.meta.url === invokedPath) {
  const requestedRoot = process.argv[2] ? resolve(process.argv[2]) : publicationRootFrom(projectRoot);
  const result = await verifyPublication(requestedRoot);
  console.log(`Verified publication: ${result.files} files, ${result.assets} hashed assets.`);
}
