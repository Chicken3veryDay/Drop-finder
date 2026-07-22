import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { verifyPagesEndpoint } from "../scripts/verify-pages-endpoint.mjs";

const json = (value) => JSON.stringify(value);
const hash = (value) => createHash("sha256").update(value).digest("hex");

const indexHtml = [
  '<link rel="manifest" href="./manifest.webmanifest">',
  '<link rel="icon" href="./icon.svg">',
  '<script type="module" src="./assets/app.js"></script>',
].join("");

const compactIndex = json({
  generation_id: "metadata-rich-generation",
  product_count: 1,
  in_stock_variant_count: 1,
  products: [{ id: "one" }],
});

const legacyCatalog = json({
  product_count: 1,
  products: [{
    id: "one",
    description: "x".repeat(6 * 1024 * 1024),
  }],
});

const payloads = new Map([
  ["", indexHtml],
  ["index.html", indexHtml],
  ["manifest.webmanifest", json({ short_name: "DropFinder", start_url: "./", scope: "./" })],
  ["app-shell.json", json({ schema_version: "dropfinder-app-shell-v1", assets: [] })],
  ["sw.js", "index.html manifest.webmanifest data/catalog.json data/status.json"],
  ["data/catalog.json", legacyCatalog],
  ["data/status.json", json({
    degraded_sources: 0,
    enabled_sources: 1,
    healthy_sources: 1,
    services: { catalog: "healthy" },
  })],
  ["data/runtime.json", json({ zero_degraded_active_services: true })],
  ["data/catalog-v4/manifest.json", json({
    schema_version: "dropfinder-catalog-manifest-v4",
    generation_id: "metadata-rich-generation",
    product_count: 1,
    in_stock_variant_count: 1,
    compact_index: { sha256: hash(compactIndex) },
  })],
  ["data/catalog-v4/index.json", compactIndex],
]);

test("default endpoint verification accepts a bounded metadata-rich legacy catalog", async () => {
  const requested = [];
  const fetchImpl = async (input) => {
    const url = new URL(input);
    requested.push(url);
    const path = url.pathname.replace(/^\/Drop-finder\/?/, "");
    assert.ok(payloads.has(path), `unexpected endpoint ${url.pathname}`);
    return new Response(payloads.get(path), {
      status: 200,
      headers: { "content-type": path.endsWith(".json") ? "application/json" : "text/plain" },
    });
  };

  const result = await verifyPagesEndpoint("https://example.test/Drop-finder/", {
    fetchImpl,
    verificationNonce: "metadata-size-regression",
  });

  assert.equal(Buffer.byteLength(legacyCatalog) > 5 * 1024 * 1024, true);
  assert.equal(result.status, "verified");
  assert.equal(result.productCount, 1);
  assert.equal(requested.length, payloads.size);
  assert.equal(requested.every((url) => url.searchParams.get("__dropfinder_verify") === "metadata-size-regression"), true);
});
