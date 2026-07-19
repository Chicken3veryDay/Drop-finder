from pathlib import Path

path = Path("web/src/platform/catalog/catalog-generation-client.js")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one anchor, found {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


replace_once(
'''        const cached = await this.cache.getLastComplete();
        if (!cached) throw error;
        const accepted = acceptCachedGeneration(cached, this.options.maxFallbackAgeMs);
        if (!accepted) {
          throw new PlatformError(
            'cache_fallback_stale',
            'Cached catalog is too old or has invalid freshness metadata',
            error,
          );
        }
        return Object.freeze({ ...accepted, source: 'cache-fallback' });
''',
'''        const cached = await this.cache.getLastComplete();
        if (!cached) throw error;
        const validation = validateCachedGeneration(cached, this.options.schemaVersion);
        if (!validation.valid) {
          let cleanupError = null;
          try { await this.cache.deleteLastComplete?.(); }
          catch (caught) { cleanupError = caught; }
          this.emit(Object.freeze({
            type: 'generation-cache-corrupt',
            generationId: typeof cached?.generationId === 'string' ? cached.generationId : null,
            code: validation.code,
            error: validation.error ?? null,
            cleanupError,
          }));
          throw error;
        }
        const accepted = acceptCachedGeneration(validation.generation, this.options.maxFallbackAgeMs);
        if (!accepted) {
          throw new PlatformError(
            'cache_fallback_stale',
            'Cached catalog is too old or has invalid freshness metadata',
            error,
          );
        }
        return Object.freeze({ ...accepted, source: 'cache-fallback' });
''')

replace_once(
'''  async getLastComplete() {
    try {
      if (!this.cacheStorage?.open) return null;
      const cache = await this.cacheStorage.open(this.cacheName);
      const response = await cache.match(this.key);
      if (!response) return null;
      const record = await response.json();
      if (record?.schemaVersion !== CACHE_RECORD_SCHEMA) return null;
      if (record.deploymentKey !== this.deploymentKey) return null;
      if (!this.owns(record.generation)) return null;
      if (!Number.isFinite(record.cachedAt)) return null;
      return Object.freeze({ ...record.generation, cachedAt: record.cachedAt });
    } catch { return null; }
  }
''',
'''  async getLastComplete() {
    if (!this.cacheStorage?.open) return null;
    let cache;
    try { cache = await this.cacheStorage.open(this.cacheName); }
    catch { return null; }
    const response = await cache.match(this.key);
    if (!response) return null;
    let record;
    try { record = await response.json(); }
    catch (error) {
      return Object.freeze({
        __cacheCorruptionCode: 'cache_record_malformed',
        __cacheCorruptionError: error,
      });
    }
    if (!record || typeof record !== 'object' || Array.isArray(record)) {
      return Object.freeze({ __cacheCorruptionCode: 'cache_record_invalid' });
    }
    if (record.schemaVersion !== CACHE_RECORD_SCHEMA) {
      return Object.freeze({ __cacheCorruptionCode: 'cache_record_schema_invalid' });
    }
    if (record.deploymentKey !== this.deploymentKey) {
      return Object.freeze({ __cacheCorruptionCode: 'cache_deployment_mismatch' });
    }
    if (!Number.isFinite(record.cachedAt)) {
      return Object.freeze({ __cacheCorruptionCode: 'cache_timestamp_invalid' });
    }
    if (!this.owns(record.generation)) {
      return Object.freeze({
        __cacheCorruptionCode: 'cache_deployment_identity_invalid',
        cachedAt: record.cachedAt,
      });
    }
    return Object.freeze({ ...record.generation, cachedAt: record.cachedAt });
  }

  async deleteLastComplete() {
    if (!this.cacheStorage?.open) return false;
    const cache = await this.cacheStorage.open(this.cacheName);
    return cache.delete(this.key);
  }
''')

replace_once(
'''export class MemoryGenerationCache {
  constructor() { this.complete = null; }
  async getLastComplete() { return this.complete; }
  async putComplete(value) {
    this.complete = Object.freeze({ ...value, cachedAt: Date.now() });
  }
}

function acceptCachedGeneration(value, maxFallbackAgeMs, now = Date.now()) {
''',
'''export class MemoryGenerationCache {
  constructor() { this.complete = null; }
  async getLastComplete() { return this.complete; }
  async putComplete(value) {
    this.complete = Object.freeze({ ...value, cachedAt: Date.now() });
  }
  async deleteLastComplete() {
    const existed = this.complete !== null;
    this.complete = null;
    return existed;
  }
}

function cacheValidationFailure(code, error = null) {
  return Object.freeze({ valid: false, code, error });
}

function validateCachedGeneration(value, expectedSchema = null) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return cacheValidationFailure('cache_value_invalid');
  }
  if (typeof value.__cacheCorruptionCode === 'string') {
    return cacheValidationFailure(value.__cacheCorruptionCode, value.__cacheCorruptionError ?? null);
  }
  const generationId = typeof value.generationId === 'string' ? value.generationId.trim() : '';
  if (!generationId) return cacheValidationFailure('cache_generation_id_missing');

  let manifest;
  try { manifest = assertGenerationEnvelope(value.manifest, expectedSchema); }
  catch (error) { return cacheValidationFailure('cache_manifest_invalid', error); }
  if (manifest.generation_id !== generationId) {
    return cacheValidationFailure('cache_generation_mismatch');
  }

  const index = value.index;
  if (!index || typeof index !== 'object' || Array.isArray(index)) {
    return cacheValidationFailure('cache_index_invalid');
  }
  if (index.generation_id !== generationId) {
    return cacheValidationFailure('cache_generation_mismatch');
  }
  if (!Array.isArray(index.products)) {
    return cacheValidationFailure('cache_products_invalid');
  }
  if (index.product_count != null
      && (!Number.isInteger(index.product_count) || index.product_count !== index.products.length)) {
    return cacheValidationFailure('cache_product_count_mismatch');
  }

  const productIds = new Set();
  const variantIds = new Set();
  let variantCount = 0;
  for (const product of index.products) {
    if (!product || typeof product !== 'object' || Array.isArray(product)) {
      return cacheValidationFailure('cache_product_invalid');
    }
    const productId = typeof product.product_id === 'string' ? product.product_id.trim() : '';
    const vendorId = typeof product.vendor_id === 'string' ? product.vendor_id.trim() : '';
    const vendorName = typeof product.vendor_name === 'string' ? product.vendor_name.trim() : '';
    const strainName = typeof product.strain_name === 'string' ? product.strain_name.trim() : '';
    if (!productId || !vendorId || !vendorName || !strainName) {
      return cacheValidationFailure('cache_product_invalid');
    }
    if (productIds.has(productId)) return cacheValidationFailure('cache_product_duplicate');
    productIds.add(productId);
    if (!Array.isArray(product.variants) || product.variants.length === 0) {
      return cacheValidationFailure('cache_variants_invalid');
    }
    const productVariantIds = new Set();
    for (const variant of product.variants) {
      if (!variant || typeof variant !== 'object' || Array.isArray(variant)) {
        return cacheValidationFailure('cache_variant_invalid');
      }
      const variantId = typeof variant.variant_id === 'string' ? variant.variant_id.trim() : '';
      const grams = Number(variant.grams);
      const price = Number(variant.current_price);
      const pricePerGram = Number(variant.price_per_gram);
      let productUrl;
      try { productUrl = new URL(String(variant.product_url ?? '')); }
      catch { return cacheValidationFailure('cache_variant_invalid'); }
      if (!variantId || !Number.isFinite(grams) || grams <= 0
          || !Number.isFinite(price) || price <= 0
          || !Number.isFinite(pricePerGram) || pricePerGram <= 0
          || variant.in_stock !== true
          || productUrl.protocol !== 'https:' || !productUrl.hostname) {
        return cacheValidationFailure('cache_variant_invalid');
      }
      if (variantIds.has(variantId)) return cacheValidationFailure('cache_variant_duplicate');
      variantIds.add(variantId);
      productVariantIds.add(variantId);
      variantCount += 1;
    }
    if (product.default_variant_id != null
        && !productVariantIds.has(String(product.default_variant_id))) {
      return cacheValidationFailure('cache_default_variant_invalid');
    }
  }
  if (index.in_stock_variant_count != null
      && (!Number.isInteger(index.in_stock_variant_count)
        || index.in_stock_variant_count !== variantCount)) {
    return cacheValidationFailure('cache_variant_count_mismatch');
  }
  return Object.freeze({ valid: true, generation: value });
}

function acceptCachedGeneration(value, maxFallbackAgeMs, now = Date.now()) {
''')

path.write_text(text, encoding="utf-8")
