import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";

const DEFAULT_MAX_BYTES = 5 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 30_000;

const normalizeBaseUrl = (value) => {
  const url = new URL(value);
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new Error(`Unsupported Pages URL protocol: ${url.protocol}`);
  }
  if (!url.pathname.endsWith("/")) url.pathname += "/";
  url.search = "";
  url.hash = "";
  return url;
};

const readBounded = async (response, label, maxBytes) => {
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}.`);
  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
    throw new Error(`${label} exceeds the ${maxBytes}-byte verification limit.`);
  }
  if (!response.body) return new Uint8Array();
  const reader = response.body.getReader();
  const parts = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > maxBytes) {
        await reader.cancel();
        throw new Error(`${label} exceeds the ${maxBytes}-byte verification limit.`);
      }
      parts.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const part of parts) {
    bytes.set(part, offset);
    offset += part.byteLength;
  }
  return bytes;
};

const fetchResource = async (fetchImpl, url, label, { maxBytes, timeoutMs }) => {
  const response = await fetchImpl(url, {
    redirect: "follow",
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
  const bytes = await readBounded(response, label, maxBytes);
  return {
    text: new TextDecoder().decode(bytes),
    evidence: {
      path: new URL(url).pathname,
      status: response.status,
      contentType: response.headers.get("content-type") || "",
      contentLength: bytes.byteLength,
      sha256: createHash("sha256").update(bytes).digest("hex"),
      cacheControl: response.headers.get("cache-control") || "",
    },
  };
};

const parseObject = (text, label) => {
  let value;
  try {
    value = JSON.parse(text);
  } catch (error) {
    throw new Error(`${label} is not valid JSON.`, { cause: error });
  }
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label} must contain a JSON object.`);
  }
  return value;
};

const verifyIndex = (index, label) => {
  if (!index.includes('href="./manifest.webmanifest"')) {
    throw new Error(`${label} does not reference the relative PWA manifest.`);
  }
  if (!index.includes('href="./icon.svg"')) {
    throw new Error(`${label} does not reference the relative application icon.`);
  }
  if (!index.includes("./assets/")) {
    throw new Error(`${label} does not reference a built application asset.`);
  }
  if (/\b(?:src|href)="\/(?!\/)/.test(index)) {
    throw new Error(`${label} contains a root-absolute asset path.`);
  }
};

export const verifyPagesEndpoint = async (
  baseUrl,
  {
    fetchImpl = globalThis.fetch,
    maxBytes = DEFAULT_MAX_BYTES,
    timeoutMs = DEFAULT_TIMEOUT_MS,
  } = {},
) => {
  if (typeof fetchImpl !== "function") throw new Error("A fetch implementation is required.");
  const root = normalizeBaseUrl(baseUrl);
  const options = { maxBytes, timeoutMs };
  const endpoints = [
    { key: "/", path: "", label: "/" },
    { key: "index.html", path: "index.html", label: "index.html" },
    { key: "manifest.webmanifest", path: "manifest.webmanifest", label: "manifest.webmanifest" },
    { key: "app-shell.json", path: "app-shell.json", label: "app-shell.json" },
    { key: "sw.js", path: "sw.js", label: "sw.js" },
    { key: "data/catalog.json", path: "data/catalog.json", label: "data/catalog.json" },
    { key: "data/status.json", path: "data/status.json", label: "data/status.json" },
    { key: "data/runtime.json", path: "data/runtime.json", label: "data/runtime.json" },
    {
      key: "data/catalog-v4/manifest.json",
      path: "data/catalog-v4/manifest.json",
      label: "catalog-v4 manifest",
    },
    {
      key: "data/catalog-v4/index.json",
      path: "data/catalog-v4/index.json",
      label: "catalog-v4 index",
    },
  ];
  const resources = Object.fromEntries(await Promise.all(endpoints.map(async ({ key, path, label }) => [
    key,
    await fetchResource(fetchImpl, new URL(path, root), label, options),
  ])));

  verifyIndex(resources["/"].text, "/");
  verifyIndex(resources["index.html"].text, "index.html");
  if (resources["/"].evidence.sha256 !== resources["index.html"].evidence.sha256) {
    throw new Error("/ and index.html do not serve identical application shell bytes.");
  }

  const manifest = parseObject(resources["manifest.webmanifest"].text, "manifest.webmanifest");
  if (manifest.short_name !== "DropFinder" || manifest.start_url !== "./" || manifest.scope !== "./") {
    throw new Error("manifest.webmanifest does not identify the subpath-safe DropFinder application.");
  }
  const appShell = parseObject(resources["app-shell.json"].text, "app-shell.json");
  if (appShell.schema_version !== "dropfinder-app-shell-v1" || !Array.isArray(appShell.assets)) {
    throw new Error("app-shell.json has an unsupported schema.");
  }
  const serviceWorker = resources["sw.js"].text;
  for (const required of ["index.html", "manifest.webmanifest", "data/catalog.json", "data/status.json"]) {
    if (!serviceWorker.includes(required)) throw new Error(`sw.js does not preserve ${required}.`);
  }

  const catalog = parseObject(resources["data/catalog.json"].text, "data/catalog.json");
  if (!Array.isArray(catalog.products) || catalog.product_count !== catalog.products.length) {
    throw new Error("data/catalog.json has an inconsistent product count.");
  }
  const status = parseObject(resources["data/status.json"].text, "data/status.json");
  if (
    status.degraded_sources !== 0 ||
    status.healthy_sources !== status.enabled_sources ||
    !status.services ||
    typeof status.services !== "object" ||
    Array.isArray(status.services) ||
    Object.values(status.services).some((value) => value !== "healthy")
  ) {
    throw new Error("data/status.json does not describe a zero-degraded healthy publication.");
  }
  const runtime = parseObject(resources["data/runtime.json"].text, "data/runtime.json");
  if (runtime.zero_degraded_active_services !== true) {
    throw new Error("data/runtime.json does not describe a zero-degraded runtime.");
  }

  const catalogV4 = parseObject(resources["data/catalog-v4/manifest.json"].text, "catalog-v4 manifest");
  const compact = parseObject(resources["data/catalog-v4/index.json"].text, "catalog-v4 index");
  if (
    catalogV4.schema_version !== "dropfinder-catalog-manifest-v4" ||
    !catalogV4.generation_id ||
    catalogV4.generation_id !== compact.generation_id ||
    catalogV4.product_count !== compact.product_count ||
    catalogV4.in_stock_variant_count !== compact.in_stock_variant_count ||
    !Array.isArray(compact.products) ||
    compact.products.length !== compact.product_count
  ) {
    throw new Error("catalog-v4 manifest and compact index are inconsistent.");
  }
  if (catalogV4.compact_index?.sha256 !== resources["data/catalog-v4/index.json"].evidence.sha256) {
    throw new Error("catalog-v4 compact index hash does not match the public bytes.");
  }

  return {
    status: "verified",
    pageUrl: root.href,
    generationId: catalogV4.generation_id,
    productCount: catalog.product_count,
    catalogV4ProductCount: catalogV4.product_count,
    variantCount: catalogV4.in_stock_variant_count,
    healthySources: status.healthy_sources,
    zeroDegraded: true,
    endpoints: Object.fromEntries(endpoints.map(({ key }) => [key, resources[key].evidence])),
  };
};

const invokedPath = process.argv[1] ? pathToFileURL(process.argv[1]).href : "";
if (import.meta.url === invokedPath) {
  const pageUrl = process.argv[2];
  if (!pageUrl) throw new Error("Usage: node verify-pages-endpoint.mjs <page-url>");
  const result = await verifyPagesEndpoint(pageUrl);
  console.log(JSON.stringify(result));
}
