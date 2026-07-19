from pathlib import Path


def replace_if_present(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old in text:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return
    if new not in text:
        raise SystemExit(f"{path}: neither old nor new state found: {old[:100]!r}")


corruption_test = Path("web/test/catalog-cache-corruption.test.mjs")
replace_if_present(
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
replace_if_present(corruption_test, "      ...(overrides.manifest ?? {}),\n", "      ...manifestOverrides,\n")
replace_if_present(corruption_test, "      ...(overrides.index ?? {}),\n", "      ...indexOverrides,\n")
replace_if_present(
    corruption_test,
    "    source: 'cache',\n    ...overrides,\n",
    "    source: 'cache',\n    ...generationOverrides,\n",
)
text = corruption_test.read_text(encoding="utf-8")
old_cases_start = "    ['missing product identity', validGeneration({ index: { products: [validProduct({ product_id: '' })] } }), 'cache_product_invalid'],\n"
old_cases_end = "    ['invalid default variant', validGeneration({ index: { products: [validProduct({ default_variant_id: 'missing' })] } }), 'cache_default_variant_invalid'],\n"
new_cases = '''    ['non-object product', validGeneration({ index: { products: [null] } }), 'cache_product_invalid'],
    ['missing product identity', validGeneration({ index: { products: [validProduct({ product_id: '' })] } }), 'cache_product_invalid'],
    ['non-array variants', validGeneration({ index: { products: [validProduct({ variants: 'not-an-array' })] } }), 'cache_variants_invalid'],
'''
if old_cases_start in text:
    start = text.index(old_cases_start)
    end = text.index(old_cases_end, start) + len(old_cases_end)
    text = text[:start] + new_cases + text[end:]
elif new_cases not in text:
    raise SystemExit("catalog-cache-corruption cases are in an unknown state")
corruption_test.write_text(text, encoding="utf-8")

client = Path("web/src/platform/catalog/catalog-generation-client.js")
client_text = client.read_text(encoding="utf-8")
validator_start_marker = "  const productIds = new Set();\n"
validator_replacement = '''  if (index.product_count != null
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
validator_scope = client_text.index("function validateCachedGeneration")
if validator_start_marker in client_text[validator_scope:]:
    start = client_text.index(validator_start_marker, validator_scope)
    end_marker = "  return Object.freeze({ valid: true, generation: value });\n"
    end = client_text.index(end_marker, start) + len(end_marker)
    client_text = client_text[:start] + validator_replacement + client_text[end:]
elif validator_replacement not in client_text:
    raise SystemExit("cached-generation validator is in an unknown state")

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
replace_if_present(
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
replace_if_present(
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
replace_if_present(
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
