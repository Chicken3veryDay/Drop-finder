import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { verifyPagesEndpoint } from "../scripts/verify-pages-endpoint.mjs";

const baseUrl = "https://example.test/Drop-finder/";
const sha256 = (value) => createHash("sha256").update(value).digest("hex");

const validBodies = () => {
  const html = `<!doctype html>
<html>
  <head>
    <link rel="manifest" href="./manifest.webmanifest" />
    <link rel="icon" href="./icon.svg" />
    <script type="module" src="./assets/app-current.js"></script>
  </head>
  <body><div id="root"></div></body>
</html>`;
  const compact = JSON.stringify({
    generation_id: "generation-test",
    product_count: 1,
    in_stock_variant_count: 1,
    products: [{ product_id: "product-1" }],
  });
  return {
    [baseUrl]: html,
    [`${baseUrl}index.html`]: html,
    [`${baseUrl}manifest.webmanifest`]: JSON.stringify({
      short_name: "DropFinder",
      start_url: "./",
      scope: "./",
    }),
    [`${baseUrl}app-shell.json`]: JSON.stringify({
      schema_version: "dropfinder-app-shell-v1",
      assets: ["./", "./index.html"],
    }),
    [`${baseUrl}sw.js`]: "index.html manifest.webmanifest data/catalog.json data/status.json",
    [`${baseUrl}data/catalog.json`]: JSON.stringify({
      product_count: 1,
      products: [{ id: "product-1" }],
    }),
    [`${baseUrl}data/status.json`]: JSON.stringify({
      degraded_sources: 0,
      healthy_sources: 2,
      enabled_sources: 2,
      services: { catalog: "healthy", publisher: "healthy" },
    }),
    [`${baseUrl}data/runtime.json`]: JSON.stringify({
      zero_degraded_active_services: true,
    }),
    [`${baseUrl}data/catalog-v4/manifest.json`]: JSON.stringify({
      schema_version: "dropfinder-catalog-manifest-v4",
      generation_id: "generation-test",
      product_count: 1,
      in_stock_variant_count: 1,
      compact_index: { sha256: sha256(compact) },
    }),
    [`${baseUrl}data/catalog-v4/index.json`]: compact,
  };
};

const fetchFrom = (bodies, overrides = {}) => async (input) => {
  const requestUrl = new URL(String(input));
  assert.ok(requestUrl.searchParams.get("__dropfinder_verify"));
  const url = `${requestUrl.origin}${requestUrl.pathname}`;
  if (url in overrides) return overrides[url];
  if (!(url in bodies)) return new Response("not found", { status: 404 });
  const contentType = url.endsWith(".json") || url.endsWith(".webmanifest")
    ? "application/json"
    : url.endsWith(".js")
      ? "text/javascript"
      : "text/html";
  return new Response(bodies[url], {
    status: 200,
    headers: { "content-type": contentType, "cache-control": "max-age=60" },
  });
};

test("accepts the current marketplace shell without the retired text marker", async () => {
  const result = await verifyPagesEndpoint(baseUrl, { fetchImpl: fetchFrom(validBodies()) });

  assert.equal(result.status, "verified");
  assert.equal(result.pageUrl, baseUrl);
  assert.equal(result.generationId, "generation-test");
  assert.equal(result.productCount, 1);
  assert.equal(result.catalogV4ProductCount, 1);
  assert.equal(result.variantCount, 1);
  assert.equal(result.healthySources, 2);
  assert.equal(result.zeroDegraded, true);
  assert.equal(result.endpoints["/"].sha256, result.endpoints["index.html"].sha256);
});

test("rejects a shell that does not reference the relative manifest", async () => {
  const bodies = validBodies();
  const invalid = '<script type="module" src="./assets/app-current.js"></script>';
  bodies[baseUrl] = invalid;
  bodies[`${baseUrl}index.html`] = invalid;

  await assert.rejects(
    verifyPagesEndpoint(baseUrl, { fetchImpl: fetchFrom(bodies) }),
    /relative PWA manifest/u,
  );
});

test("rejects inconsistent root and index shell bytes", async () => {
  const bodies = validBodies();
  bodies[`${baseUrl}index.html`] = bodies[`${baseUrl}index.html`].replace("app-current", "app-other");

  await assert.rejects(
    verifyPagesEndpoint(baseUrl, { fetchImpl: fetchFrom(bodies) }),
    /identical application shell bytes/u,
  );
});

test("rejects an inconsistent catalog product count", async () => {
  const bodies = validBodies();
  bodies[`${baseUrl}data/catalog.json`] = JSON.stringify({ product_count: 2, products: [{}] });

  await assert.rejects(
    verifyPagesEndpoint(baseUrl, { fetchImpl: fetchFrom(bodies) }),
    /inconsistent product count/u,
  );
});

test("rejects a degraded publication status", async () => {
  const bodies = validBodies();
  bodies[`${baseUrl}data/status.json`] = JSON.stringify({
    degraded_sources: 1,
    healthy_sources: 1,
    enabled_sources: 2,
    services: { catalog: "degraded" },
  });

  await assert.rejects(
    verifyPagesEndpoint(baseUrl, { fetchImpl: fetchFrom(bodies) }),
    /zero-degraded healthy publication/u,
  );
});

test("rejects HTTP failures", async () => {
  const bodies = validBodies();
  const failingUrl = `${baseUrl}data/status.json`;

  await assert.rejects(
    verifyPagesEndpoint(baseUrl, {
      fetchImpl: fetchFrom(bodies, { [failingUrl]: new Response("unavailable", { status: 503 }) }),
    }),
    /HTTP 503/u,
  );
});

test("stream-bounds oversized responses without a content-length header", async () => {
  const bodies = validBodies();
  const oversizedUrl = `${baseUrl}data/catalog.json`;

  await assert.rejects(
    verifyPagesEndpoint(baseUrl, {
      maxBytes: 512,
      fetchImpl: fetchFrom(bodies, {
        [oversizedUrl]: new Response("x".repeat(1024), { status: 200 }),
      }),
    }),
    /verification limit/u,
  );
});
