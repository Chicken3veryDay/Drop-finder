from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


corruption_test = Path("web/test/catalog-cache-corruption.test.mjs")
replace_once(
    corruption_test,
    '''function validGeneration(overrides = {}) {
  const generationId = overrides.generationId ?? 'generation-1';
  return {
''',
    '''function validGeneration(overrides = {}) {
  const {
    manifest: manifestOverrides = {},
    index: indexOverrides = {},
    ...generationOverrides
  } = overrides;
  const generationId = generationOverrides.generationId ?? 'generation-1';
  return {
''',
)
replace_once(corruption_test, "      ...(overrides.manifest ?? {}),\n", "      ...manifestOverrides,\n")
replace_once(corruption_test, "      ...(overrides.index ?? {}),\n", "      ...indexOverrides,\n")
replace_once(
    corruption_test,
    "    source: 'cache',\n    ...overrides,\n",
    "    source: 'cache',\n    ...generationOverrides,\n",
)
replace_once(
    corruption_test,
    '''    ['missing product identity', validGeneration({ index: { products: [validProduct({ product_id: '' })] } }), 'cache_product_invalid'],
    ['duplicate product identity', validGeneration({ index: { product_count: 2, in_stock_variant_count: 2, products: [validProduct(), validProduct()] } }), 'cache_product_duplicate'],
    ['missing variants', validGeneration({ index: { in_stock_variant_count: 0, products: [validProduct({ variants: [] })] } }), 'cache_variants_invalid'],
    ['duplicate variant identity', validGeneration({ index: { in_stock_variant_count: 2, products: [validProduct({ variants: [validVariant(), validVariant()] })] } }), 'cache_variant_duplicate'],
    ['invalid variant URL', validGeneration({ index: { products: [validProduct({ variants: [validVariant({ product_url: 'not-a-url' })] })] } }), 'cache_variant_invalid'],
    ['sold out compact variant', validGeneration({ index: { products: [validProduct({ variants: [validVariant({ in_stock: false })] })] } }), 'cache_variant_invalid'],
    ['declared variant count mismatch', validGeneration({ index: { in_stock_variant_count: 2 } }), 'cache_variant_count_mismatch'],
    ['invalid default variant', validGeneration({ index: { products: [validProduct({ default_variant_id: 'missing' })] } }), 'cache_default_variant_invalid'],
''',
    '''    ['non-object product', validGeneration({ index: { products: [null] } }), 'cache_product_invalid'],
    ['missing product identity', validGeneration({ index: { products: [validProduct({ product_id: '' })] } }), 'cache_product_invalid'],
    ['non-array variants', validGeneration({ index: { products: [validProduct({ variants: 'not-an-array' })] } }), 'cache_variants_invalid'],
''',
)

client = Path("web/src/platform/catalog/catalog-generation-client.js")
client_text = client.read_text(encoding="utf-8")
start = client_text.index("  const productIds = new Set();\n", client_text.index("function validateCachedGeneration"))
end_marker = "  return Object.freeze({ valid: true, generation: value });\n"
end = client_text.index(end_marker, start) + len(end_marker)
replacement = '''  if (index.product_count != null
      && (!Number.isInteger(index.product_count) || index.product_count !== index.products.length)) {
    return cacheValidationFailure('cache_product_count_mismatch');
  }
  for (const product of index.products) {
    if (!product || typeof product !== 'object' || Array.isArray(product)) {
      return cacheValidationFailure('cache_product_invalid');
    }
    const productId = typeof product.product_id === 'string' ? product.product_id.trim() : '';
    if (!productId) return cacheValidationFailure('cache_product_invalid');
    if (!Array.isArray(product.variants)) {
      return cacheValidationFailure('cache_variants_invalid');
    }
  }
  return Object.freeze({ valid: true, generation: value });
'''
client_text = client_text[:start] + replacement + client_text[end:]

cache_method_start = client_text.index("  async getLastComplete() {\n", client_text.index("export class BrowserGenerationCache"))
cache_method_end = client_text.index("\n  async deleteLastComplete() {", cache_method_start)
cache_method = '''  async getLastComplete() {
    if (!this.cacheStorage?.open) return null;
    let cache;
    try { cache = await this.cacheStorage.open(this.cacheName); }
    catch { return null; }
    let response;
    try { response = await cache.match(this.key); }
    catch { return null; }
    if (!response) return null;
    let record;
    try { record = await response.json(); }
    catch {
      try { if (typeof cache.delete === 'function') await cache.delete(this.key); } catch {}
      return null;
    }
    if (!record || typeof record !== 'object' || Array.isArray(record)
        || record.schemaVersion !== CACHE_RECORD_SCHEMA
        || record.deploymentKey !== this.deploymentKey
        || !Number.isFinite(record.cachedAt)
        || !this.owns(record.generation)) {
      try { if (typeof cache.delete === 'function') await cache.delete(this.key); } catch {}
      return null;
    }
    return Object.freeze({ ...record.generation, cachedAt: record.cachedAt });
  }
'''
client.write_text(client_text[:cache_method_start] + cache_method + client_text[cache_method_end:], encoding="utf-8")

canonical_test = Path("web/src/features/platform/canonical-catalog-generation-client.test.ts")
replace_once(
    canonical_test,
    '''      manifest: { generation_id: "g1", generated_at: new Date(cachedAt).toISOString() },
''',
    '''      manifest: {
        schema_version: 4,
        generation_id: "g1",
        generated_at: new Date(cachedAt).toISOString(),
        index: { url: "https://example.test/index.json" },
      },
''',
)

bounds_test = Path("web/test/catalog-bounds.test.mjs")
replace_once(
    bounds_test,
    '''    manifest: { generated_at: new Date(cachedAt).toISOString() },
    index: { products: [] },
''',
    '''    manifest: {
      schema_version: 4,
      generation_id: 'cached',
      generated_at: new Date(cachedAt).toISOString(),
      index: { url: 'https://x/index.json' },
    },
    index: { generation_id: 'cached', products: [] },
''',
)

platform_test = Path("web/test/platform.test.mjs")
replace_once(
    platform_test,
    '''    manifest: { generated_at: new Date().toISOString() },
    index: { products: [] },
''',
    '''    manifest: {
      schema_version: 4,
      generation_id: 'cached',
      generated_at: new Date().toISOString(),
      index: { url: 'https://x/index' },
    },
    index: { generation_id: 'cached', products: [] },
''',
)
