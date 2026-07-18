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

const readBoundedText = async (response, label, maxBytes) => {
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}.`);

  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
    throw new Error(`${label} exceeds the ${maxBytes}-byte verification limit.`);
  }

  if (!response.body) return "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
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
      parts.push(decoder.decode(value, { stream: true }));
    }
  } finally {
    reader.releaseLock();
  }

  parts.push(decoder.decode());
  return parts.join("");
};

const fetchText = async (fetchImpl, url, label, { maxBytes, timeoutMs }) => {
  const response = await fetchImpl(url, {
    redirect: "follow",
    signal: AbortSignal.timeout(timeoutMs),
  });
  return readBoundedText(response, label, maxBytes);
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

  const [index, manifestText, catalogText, statusText] = await Promise.all([
    fetchText(fetchImpl, root, "index.html", options),
    fetchText(fetchImpl, new URL("manifest.webmanifest", root), "manifest.webmanifest", options),
    fetchText(fetchImpl, new URL("data/catalog.json", root), "data/catalog.json", options),
    fetchText(fetchImpl, new URL("data/status.json", root), "data/status.json", options),
  ]);

  if (!index.includes('href="./manifest.webmanifest"')) {
    throw new Error("index.html does not reference the relative PWA manifest.");
  }
  if (!index.includes('href="./icon.svg"')) {
    throw new Error("index.html does not reference the relative application icon.");
  }
  if (!index.includes("./assets/")) {
    throw new Error("index.html does not reference a built application asset.");
  }
  if (/\b(?:src|href)="\/(?!\/)/.test(index)) {
    throw new Error("index.html contains a root-absolute asset path.");
  }

  const manifest = parseObject(manifestText, "manifest.webmanifest");
  if (manifest.short_name !== "DropFinder" || manifest.start_url !== "./" || manifest.scope !== "./") {
    throw new Error("manifest.webmanifest does not identify the subpath-safe DropFinder application.");
  }

  const catalog = parseObject(catalogText, "data/catalog.json");
  if (!Array.isArray(catalog.products) || catalog.product_count !== catalog.products.length) {
    throw new Error("data/catalog.json has an inconsistent product count.");
  }

  const status = parseObject(statusText, "data/status.json");
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

  return {
    pageUrl: root.href,
    productCount: catalog.product_count,
    healthySources: status.healthy_sources,
  };
};

const invokedPath = process.argv[1] ? pathToFileURL(process.argv[1]).href : "";
if (import.meta.url === invokedPath) {
  const pageUrl = process.argv[2];
  if (!pageUrl) throw new Error("Usage: node verify-pages-endpoint.mjs <page-url>");
  const result = await verifyPagesEndpoint(pageUrl);
  console.log(JSON.stringify(result));
}
