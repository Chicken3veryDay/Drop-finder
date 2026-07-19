import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { verifyCatalogV4Publication } from "../scripts/verify-catalog-v4-publication.mjs";
import { verifyPagesEndpoint } from "../scripts/verify-pages-endpoint.mjs";

const json = (value) => `${JSON.stringify(value, null, 2)}\n`;
const digest = (value) => createHash("sha256").update(value).digest("hex");

const createV4 = async (root, generation = "generation-test") => {
  const directory = join(root, "data", "catalog-v4");
  await mkdir(join(directory, "details"), { recursive: true });
  const index = json({
    generation_id: generation,
    product_count: 1,
    in_stock_variant_count: 2,
    products: [{ product_id: "p1", variants: [{ variant_id: "a" }, { variant_id: "b" }] }],
  });
  const vendors = json({ generation_id: generation, vendors: [] });
  const rejections = json({ generation_id: generation, count: 0, products: [] });
  const details = json({ generation_id: generation, products: [{ product_id: "p1" }] });
  await writeFile(join(directory, "index.json"), index);
  await writeFile(join(directory, "vendors.json"), vendors);
  await writeFile(join(directory, "rejections.json"), rejections);
  await writeFile(join(directory, "details", "000.json"), details);
  const manifest = {
    schema_version: "dropfinder-catalog-manifest-v4",
    generation_id: generation,
    generated_at: "2026-07-19T00:00:00+00:00",
    product_count: 1,
    in_stock_variant_count: 2,
    compact_index: { path: "data/catalog-v4/index.json", sha256: digest(index) },
    vendor_profiles: { path: "data/catalog-v4/vendors.json", sha256: digest(vendors) },
    rejections: { path: "data/catalog-v4/rejections.json", sha256: digest(rejections) },
    product_detail_shards: [{
      path: "data/catalog-v4/details/000.json",
      product_count: 1,
      sha256: digest(details),
    }],
  };
  await writeFile(join(directory, "manifest.json"), json(manifest));
  return { manifest, index };
};

test("catalog v4 verifier checks every referenced hash and count", async () => {
  const root = await mkdtemp(join(tmpdir(), "dropfinder-v4-"));
  try {
    await createV4(root);
    const result = await verifyCatalogV4Publication(root);
    assert.equal(result.generationId, "generation-test");
    assert.equal(result.productCount, 1);
    await writeFile(join(root, "data", "catalog-v4", "details", "000.json"), json({ generation_id: "generation-test", products: [] }));
    await assert.rejects(() => verifyCatalogV4Publication(root), /hash mismatch/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("public endpoint verifier returns generation and byte-level endpoint evidence", async () => {
  const generation = "generation-endpoint";
  const compactText = json({
    generation_id: generation,
    product_count: 1,
    in_stock_variant_count: 1,
    products: [{ product_id: "p1" }],
  });
  const resources = new Map([
    ["index.html", '<link rel="manifest" href="./manifest.webmanifest"><link rel="icon" href="./icon.svg"><script type="module" src="./assets/app-abcdef.js"></script>'],
    ["manifest.webmanifest", json({ short_name: "DropFinder", start_url: "./", scope: "./" })],
    ["app-shell.json", json({ schema_version: "dropfinder-app-shell-v1", assets: ["./"] })],
    ["sw.js", "index.html manifest.webmanifest data/catalog.json data/status.json"],
    ["data/catalog.json", json({ product_count: 1, products: [{ id: "p1" }] })],
    ["data/status.json", json({
      degraded_sources: 0,
      healthy_sources: 1,
      enabled_sources: 1,
      services: { publisher: "healthy" },
    })],
    ["data/runtime.json", json({ zero_degraded_active_services: true })],
    ["data/catalog-v4/manifest.json", json({
      schema_version: "dropfinder-catalog-manifest-v4",
      generation_id: generation,
      product_count: 1,
      in_stock_variant_count: 1,
      compact_index: { sha256: digest(compactText) },
    })],
    ["data/catalog-v4/index.json", compactText],
  ]);
  const fetchImpl = async (url) => {
    const path = new URL(url).pathname.split("/Drop-finder/").at(-1) || "index.html";
    const body = resources.get(path);
    assert.notEqual(body, undefined, `unexpected endpoint ${path}`);
    return new Response(body, {
      status: 200,
      headers: {
        "content-type": path.endsWith(".json") ? "application/json" : "text/plain",
        "cache-control": "max-age=60",
      },
    });
  };
  const result = await verifyPagesEndpoint("https://example.test/Drop-finder/", { fetchImpl });
  assert.equal(result.generationId, generation);
  assert.equal(result.status, "verified");
  assert.equal(result.endpoints["data/catalog-v4/index.json"].sha256, digest(compactText));
  assert.equal(result.endpoints["data/catalog.json"].status, 200);
});
