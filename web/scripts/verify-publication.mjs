import { readFile, stat } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { listPublicationFiles, publicationRootFrom } from "./publication-utils.mjs";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const publicationBaseUrl = new URL("https://publication.invalid/Drop-finder/");

const requiredFiles = [
  "index.html",
  "manifest.webmanifest",
  "icon.svg",
  "sw.js",
  "app-shell.json",
  "assets/vite-manifest.json",
  "data/catalog.json",
  "data/status.json",
  "data/runtime.json",
];

const assertFile = async (publicationRoot, relativePath) => {
  let details;
  try {
    details = await stat(resolve(publicationRoot, relativePath));
  } catch (error) {
    if (error?.code === "ENOENT") throw new Error(`Missing or empty publication file: ${relativePath}`);
    throw error;
  }
  if (!details.isFile() || details.size === 0) throw new Error(`Missing or empty publication file: ${relativePath}`);
};

const parseStartTags = (html) => {
  const tags = [];
  let cursor = 0;
  while (cursor < html.length) {
    const opening = html.indexOf("<", cursor);
    if (opening === -1) break;
    if (html.startsWith("<!--", opening)) {
      const closing = html.indexOf("-->", opening + 4);
      cursor = closing === -1 ? html.length : closing + 3;
      continue;
    }

    let index = opening + 1;
    if (html[index] === "/" || html[index] === "!" || html[index] === "?") {
      const closing = html.indexOf(">", index + 1);
      cursor = closing === -1 ? html.length : closing + 1;
      continue;
    }

    while (/\s/.test(html[index] || "")) index += 1;
    const nameStart = index;
    while (/[A-Za-z0-9:-]/.test(html[index] || "")) index += 1;
    if (index === nameStart) {
      cursor = opening + 1;
      continue;
    }

    const name = html.slice(nameStart, index).toLowerCase();
    const attributes = new Map();
    let terminated = false;
    while (index < html.length) {
      while (/\s/.test(html[index] || "")) index += 1;
      if (html[index] === ">") {
        index += 1;
        terminated = true;
        break;
      }
      if (html[index] === "/" && html[index + 1] === ">") {
        index += 2;
        terminated = true;
        break;
      }

      const attributeStart = index;
      while (index < html.length && !/[\s=/>]/.test(html[index])) index += 1;
      if (index === attributeStart) {
        index += 1;
        continue;
      }
      const attributeName = html.slice(attributeStart, index).toLowerCase();
      while (/\s/.test(html[index] || "")) index += 1;
      let value = "";
      if (html[index] === "=") {
        index += 1;
        while (/\s/.test(html[index] || "")) index += 1;
        const quote = html[index];
        if (quote === '"' || quote === "'") {
          index += 1;
          const valueStart = index;
          while (index < html.length && html[index] !== quote) index += 1;
          value = html.slice(valueStart, index);
          if (html[index] === quote) index += 1;
        } else {
          const valueStart = index;
          while (index < html.length && !/[\s>]/.test(html[index])) index += 1;
          value = html.slice(valueStart, index);
        }
      }
      if (!attributes.has(attributeName)) attributes.set(attributeName, value);
    }

    if (!terminated) break;
    tags.push({ name, attributes });
    cursor = index;
    if (name === "script") {
      const closing = html.toLowerCase().indexOf("</script", cursor);
      if (closing !== -1) cursor = closing;
    }
  }
  return tags;
};

const localPublicationPath = (reference, context) => {
  const raw = reference.trim();
  if (!raw || raw.startsWith("#")) return null;
  if (raw.startsWith("/") || raw.includes("\\")) {
    throw new Error(`${context} must use a subpath-safe relative URL: ${reference}`);
  }

  let url;
  try {
    url = new URL(raw, new URL("index.html", publicationBaseUrl));
  } catch {
    throw new Error(`${context} contains an invalid URL: ${reference}`);
  }
  if (url.origin !== publicationBaseUrl.origin) return null;
  if (!url.pathname.startsWith(publicationBaseUrl.pathname)) {
    throw new Error(`${context} escapes the publication root: ${reference}`);
  }

  let decodedPath;
  try {
    decodedPath = decodeURIComponent(url.pathname.slice(publicationBaseUrl.pathname.length));
  } catch {
    throw new Error(`${context} contains invalid URL encoding: ${reference}`);
  }
  if (!decodedPath || decodedPath.includes("\\") || decodedPath.includes("\0")) {
    throw new Error(`${context} contains an invalid local path: ${reference}`);
  }
  return decodedPath;
};

const ensurePathContained = (publicationRoot, relativePath, context) => {
  const absolutePath = resolve(publicationRoot, relativePath);
  const containedPath = relative(publicationRoot, absolutePath);
  const parentPrefix = `..${process.platform === "win32" ? "\\" : "/"}`;
  if (!containedPath || containedPath === ".." || containedPath.startsWith(parentPrefix) || isAbsolute(containedPath)) {
    throw new Error(`${context} escapes the publication root: ${relativePath}`);
  }
  return relativePath.replaceAll("\\", "/");
};

const readJsonObject = async (path, label) => {
  let value;
  try {
    value = JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    throw new Error(`${label} must contain valid JSON.`, { cause: error });
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must contain a JSON object.`);
  return value;
};

const assertSameSet = (actual, expected, label) => {
  const missing = [...expected].filter((value) => !actual.has(value));
  const unexpected = [...actual].filter((value) => !expected.has(value));
  if (missing.length || unexpected.length) {
    throw new Error(`${label} mismatch; missing: ${missing.join(", ") || "none"}; unexpected: ${unexpected.join(", ") || "none"}.`);
  }
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
  const localReferences = [];
  for (const tag of parseStartTags(index)) {
    const attribute = tag.name === "script" ? "src" : tag.name === "link" ? "href" : null;
    if (!attribute || !tag.attributes.has(attribute)) continue;
    const rawReference = tag.attributes.get(attribute);
    const relativePath = localPublicationPath(rawReference, `index.html ${tag.name}[${attribute}]`);
    if (!relativePath) continue;
    const safePath = ensurePathContained(root, relativePath, `index.html ${tag.name}[${attribute}]`);
    await assertFile(root, safePath);
    const rel = (tag.attributes.get("rel") || "").toLowerCase().split(/\s+/).filter(Boolean);
    localReferences.push({
      tag: tag.name,
      rel,
      type: (tag.attributes.get("type") || "").toLowerCase(),
      path: safePath,
    });
  }

  if (!localReferences.some((reference) => reference.tag === "link" && reference.rel.includes("manifest") && reference.path === "manifest.webmanifest")) {
    throw new Error("index.html must reference ./manifest.webmanifest with a manifest link.");
  }
  if (!localReferences.some((reference) => reference.tag === "link" && reference.rel.includes("icon") && reference.path === "icon.svg")) {
    throw new Error("index.html must reference ./icon.svg with an icon link.");
  }
  if (index.includes("src/app/main.tsx")) throw new Error("index.html still references the development entry point.");

  const viteManifest = await readJsonObject(resolve(root, "assets/vite-manifest.json"), "Vite manifest");
  const manifestFiles = new Set();
  const entryFiles = new Set();
  const entryCss = new Set();
  const manifestRecords = Object.entries(viteManifest);
  if (manifestRecords.length === 0) throw new Error("Vite manifest must contain at least one record.");

  for (const [key, record] of manifestRecords) {
    if (!record || typeof record !== "object" || Array.isArray(record)) throw new Error(`Vite manifest record ${key} must be an object.`);
    const imports = record.imports ?? [];
    const dynamicImports = record.dynamicImports ?? [];
    if (!Array.isArray(imports) || !Array.isArray(dynamicImports)) throw new Error(`Vite manifest record ${key} contains an invalid import list.`);
    for (const linkedKey of [...imports, ...dynamicImports]) {
      if (typeof linkedKey !== "string" || !Object.hasOwn(viteManifest, linkedKey)) {
        throw new Error(`Vite manifest record ${key} references missing record ${linkedKey}.`);
      }
    }
    const css = record.css ?? [];
    const assets = record.assets ?? [];
    if (!Array.isArray(css) || !Array.isArray(assets)) throw new Error(`Vite manifest record ${key} contains an invalid asset list.`);
    for (const field of [record.file, ...css, ...assets]) {
      if (typeof field !== "string" || field.length === 0) throw new Error(`Vite manifest record ${key} contains an invalid asset path.`);
      const localPath = localPublicationPath(`./${field.replace(/^\.\//, "")}`, `Vite manifest record ${key}`);
      const safePath = ensurePathContained(root, localPath, `Vite manifest record ${key}`);
      await assertFile(root, safePath);
      manifestFiles.add(safePath);
    }
    if (record.isEntry) {
      if (typeof record.file !== "string" || !record.file) throw new Error(`Vite entry ${key} does not declare a file.`);
      entryFiles.add(record.file.replace(/^\.\//, ""));
      for (const stylesheet of css) entryCss.add(stylesheet.replace(/^\.\//, ""));
    }
  }
  if (entryFiles.size === 0) throw new Error("Vite manifest does not declare an application entry.");

  const htmlModuleEntries = new Set(localReferences
    .filter((reference) => reference.tag === "script" && reference.type === "module" && reference.path.startsWith("assets/"))
    .map((reference) => reference.path));
  const htmlStylesheets = new Set(localReferences
    .filter((reference) => reference.tag === "link" && reference.rel.includes("stylesheet") && reference.path.startsWith("assets/"))
    .map((reference) => reference.path));
  assertSameSet(htmlModuleEntries, entryFiles, "HTML module entries and Vite entries");
  assertSameSet(htmlStylesheets, entryCss, "HTML stylesheets and Vite entry CSS");

  const appShell = await readJsonObject(resolve(root, "app-shell.json"), "Application shell manifest");
  if (appShell.schema_version !== "dropfinder-app-shell-v1" || !Array.isArray(appShell.assets)) {
    throw new Error("Application shell manifest has an unsupported schema.");
  }
  const shellFiles = new Set();
  for (const asset of appShell.assets) {
    if (asset === "./") continue;
    if (typeof asset !== "string") throw new Error("Application shell manifest contains a non-string asset.");
    const localPath = localPublicationPath(asset, "Application shell manifest");
    const safePath = ensurePathContained(root, localPath, "Application shell manifest");
    await assertFile(root, safePath);
    shellFiles.add(safePath);
  }
  for (const reference of localReferences) {
    if (!shellFiles.has(reference.path)) throw new Error(`Application shell manifest omits index dependency: ${reference.path}`);
  }
  for (const entryFile of entryFiles) {
    if (!manifestFiles.has(entryFile)) throw new Error(`Vite entry is not part of the validated manifest closure: ${entryFile}`);
  }

  const manifest = await readJsonObject(resolve(root, "manifest.webmanifest"), "PWA manifest");
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
