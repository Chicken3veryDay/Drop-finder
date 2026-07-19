import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

const readObject = async (path, label) => {
  let value;
  try {
    value = JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    throw new Error(`${label} must contain valid interoperable JSON.`, { cause: error });
  }
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label} must contain a JSON object.`);
  }
  return value;
};

const safeReference = (root, value, label) => {
  if (typeof value !== "string" || !value.startsWith("data/catalog-v4/")) {
    throw new Error(`${label} must remain under data/catalog-v4/.`);
  }
  if (value.includes("\\") || value.includes("\0") || value.split("/").includes("..")) {
    throw new Error(`${label} contains an unsafe path.`);
  }
  const absolute = resolve(root, value);
  const contained = relative(root, absolute);
  if (!contained || contained === ".." || contained.startsWith("../") || isAbsolute(contained)) {
    throw new Error(`${label} escapes the publication root.`);
  }
  return absolute;
};

const verifyRecord = async (root, record, generationId, label) => {
  if (!record || Array.isArray(record) || typeof record !== "object") {
    throw new Error(`${label} must be a manifest record.`);
  }
  const path = safeReference(root, record.path, `${label}.path`);
  const expected = String(record.sha256 || "");
  if (!/^[0-9a-f]{64}$/.test(expected)) throw new Error(`${label}.sha256 is invalid.`);
  const details = await stat(path);
  if (!details.isFile() || details.size === 0) throw new Error(`${label} references a missing file.`);
  const bytes = await readFile(path);
  const actual = sha256(bytes);
  if (actual !== expected) throw new Error(`${label} hash mismatch for ${record.path}.`);
  let payload;
  try {
    payload = JSON.parse(bytes.toString("utf8"));
  } catch (error) {
    throw new Error(`${label} is not valid JSON.`, { cause: error });
  }
  if (!payload || Array.isArray(payload) || typeof payload !== "object") {
    throw new Error(`${label} payload must be an object.`);
  }
  if (payload.generation_id !== generationId) {
    throw new Error(`${label} generation does not match the manifest.`);
  }
  return payload;
};

export const verifyCatalogV4Publication = async (publicationRoot) => {
  const root = resolve(publicationRoot);
  const manifestPath = resolve(root, "data/catalog-v4/manifest.json");
  const manifest = await readObject(manifestPath, "Catalog v4 manifest");
  if (manifest.schema_version !== "dropfinder-catalog-manifest-v4") {
    throw new Error("Catalog v4 manifest schema is unsupported.");
  }
  const generationId = String(manifest.generation_id || "");
  if (!generationId) throw new Error("Catalog v4 manifest has no generation ID.");
  const productCount = Number(manifest.product_count);
  const variantCount = Number(manifest.in_stock_variant_count);
  if (!Number.isInteger(productCount) || productCount < 1) {
    throw new Error("Catalog v4 manifest product count is invalid.");
  }
  if (!Number.isInteger(variantCount) || variantCount < 1) {
    throw new Error("Catalog v4 manifest variant count is invalid.");
  }

  const compact = await verifyRecord(root, manifest.compact_index, generationId, "Compact index");
  await verifyRecord(root, manifest.vendor_profiles, generationId, "Vendor profiles");
  await verifyRecord(root, manifest.rejections, generationId, "Rejections");
  if (compact.product_count !== productCount || compact.in_stock_variant_count !== variantCount) {
    throw new Error("Catalog v4 compact index counts do not match the manifest.");
  }
  if (!Array.isArray(compact.products) || compact.products.length !== productCount) {
    throw new Error("Catalog v4 compact index rows do not match its product count.");
  }

  const detailRecords = manifest.product_detail_shards;
  if (!Array.isArray(detailRecords) || detailRecords.length === 0) {
    throw new Error("Catalog v4 manifest must reference detail shards.");
  }
  let detailProductCount = 0;
  const seenPaths = new Set();
  for (const [index, record] of detailRecords.entries()) {
    if (seenPaths.has(record?.path)) throw new Error(`Duplicate detail shard path: ${record?.path}`);
    seenPaths.add(record?.path);
    const detail = await verifyRecord(root, record, generationId, `Detail shard ${index}`);
    const declared = Number(record.product_count);
    if (!Number.isInteger(declared) || declared < 0) {
      throw new Error(`Detail shard ${index} has an invalid product count.`);
    }
    if (!Array.isArray(detail.products) || detail.products.length !== declared) {
      throw new Error(`Detail shard ${index} rows do not match the manifest.`);
    }
    detailProductCount += declared;
  }
  if (detailProductCount !== productCount) {
    throw new Error("Catalog v4 detail shard counts do not match the manifest.");
  }

  return {
    generationId,
    productCount,
    variantCount,
    detailShardCount: detailRecords.length,
    manifestSha256: sha256(await readFile(manifestPath)),
  };
};

const invokedPath = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : "";
if (import.meta.url === invokedPath) {
  const root = process.argv[2] ? resolve(process.argv[2]) : resolve("cloud_pages");
  const result = await verifyCatalogV4Publication(root);
  console.log(JSON.stringify(result));
}
