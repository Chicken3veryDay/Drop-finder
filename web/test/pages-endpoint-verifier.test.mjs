import assert from "node:assert/strict";
import test from "node:test";

import { verifyPagesEndpoint } from "../scripts/verify-pages-endpoint.mjs";

const baseUrl = "https://example.test/Drop-finder/";

const validBodies = () => ({
  [baseUrl]: `<!doctype html>
<html>
  <head>
    <link rel="manifest" href="./manifest.webmanifest" />
    <link rel="icon" href="./icon.svg" />
    <script type="module" src="./assets/app-current.js"></script>
  </head>
  <body><div id="root"></div></body>
</html>`,
  [`${baseUrl}manifest.webmanifest`]: JSON.stringify({
    short_name: "DropFinder",
    start_url: "./",
    scope: "./",
  }),
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
});

const fetchFrom = (bodies, overrides = {}) => async (input) => {
  const url = String(input);
  if (url in overrides) return overrides[url];
  if (!(url in bodies)) return new Response("not found", { status: 404 });
  return new Response(bodies[url], {
    status: 200,
    headers: { "content-type": url.endsWith(".json") ? "application/json" : "text/html" },
  });
};

test("accepts the current marketplace shell without the retired text marker", async () => {
  const result = await verifyPagesEndpoint(baseUrl, { fetchImpl: fetchFrom(validBodies()) });

  assert.deepEqual(result, {
    pageUrl: baseUrl,
    productCount: 1,
    healthySources: 2,
  });
});

test("rejects a shell that does not reference the relative manifest", async () => {
  const bodies = validBodies();
  bodies[baseUrl] = '<script type="module" src="./assets/app-current.js"></script>';

  await assert.rejects(
    verifyPagesEndpoint(baseUrl, { fetchImpl: fetchFrom(bodies) }),
    /relative PWA manifest/u,
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
      maxBytes: 32,
      fetchImpl: fetchFrom(bodies, {
        [oversizedUrl]: new Response("x".repeat(64), { status: 200 }),
      }),
    }),
    /verification limit/u,
  );
});
