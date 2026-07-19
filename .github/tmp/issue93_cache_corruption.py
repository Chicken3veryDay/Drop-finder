from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


client = "web/src/platform/catalog/catalog-generation-client.js"
replace_once(
    client,
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
        let structurallyValid;
        try {
          structurallyValid = validateCachedGeneration(cached, this.options.schemaVersion);
        } catch (cacheError) {
          try { await this.cache.deleteLastComplete?.(); } catch { /* best-effort quarantine */ }
          this.emit(Object.freeze({
            type: 'generation-cache-corrupt',
            generationId: typeof cached?.generationId === 'string' ? cached.generationId : null,
            code: cacheError?.code ?? 'cache_corrupt',
            error: cacheError,
          }));
          throw error;
        }
        const accepted = acceptCachedGeneration(structurallyValid, this.options.maxFallbackAgeMs);
        if (!accepted) {
          throw new PlatformError(
            'cache_fallback_stale',
            'Cached catalog is too old or has invalid freshness metadata',
            error,
          );
        }
        return Object.freeze({ ...accepted, source: 'cache-fallback' });
''',
)
replace_once(
    client,
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

  async putComplete(value) {
''',
    '''  async getLastComplete() {
    let cache = null;
    try {
      if (!this.cacheStorage?.open) return null;
      cache = await this.cacheStorage.open(this.cacheName);
      const response = await cache.match(this.key);
      if (!response) return null;
      const record = await response.json();
      if (record?.schemaVersion !== CACHE_RECORD_SCHEMA
        || record.deploymentKey !== this.deploymentKey
        || !this.owns(record.generation)
        || !Number.isFinite(record.cachedAt)) {
        await this.deleteLastComplete(cache);
        return null;
      }
      return Object.freeze({ ...record.generation, cachedAt: record.cachedAt });
    } catch {
      try { await this.deleteLastComplete(cache); } catch { /* best-effort quarantine */ }
      return null;
    }
  }

  async deleteLastComplete(openCache = null) {
    if (!openCache && !this.cacheStorage?.open) return false;
    const cache = openCache ?? await this.cacheStorage.open(this.cacheName);
    return typeof cache.delete === 'function' ? cache.delete(this.key) : false;
  }

  async putComplete(value) {
''',
)
replace_once(
    client,
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
  async deleteLastComplete() { this.complete = null; return true; }
  async putComplete(value) {
    this.complete = Object.freeze({ ...value, cachedAt: Date.now() });
  }
}

function validateCachedGeneration(value, expectedSchema) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new PlatformError('cache_invalid_generation', 'Cached catalog generation is not an object');
  }
  const generationId = typeof value.generationId === 'string' ? value.generationId.trim() : '';
  if (!generationId) {
    throw new PlatformError('cache_invalid_generation', 'Cached catalog generation ID is missing');
  }
  const manifest = assertGenerationEnvelope(value.manifest, expectedSchema);
  if (manifest.generation_id !== generationId) {
    throw new PlatformError('cache_generation_mismatch', 'Cached manifest generation does not match its envelope');
  }
  const index = value.index;
  if (!index || typeof index !== 'object' || Array.isArray(index)) {
    throw new PlatformError('cache_invalid_index', 'Cached catalog index is not an object');
  }
  if (index.generation_id !== generationId) {
    throw new PlatformError('cache_generation_mismatch', 'Cached index generation does not match its envelope');
  }
  if (!Array.isArray(index.products)) {
    throw new PlatformError('cache_invalid_index', 'Cached catalog index products are missing');
  }
  for (const product of index.products) {
    if (!product || typeof product !== 'object' || Array.isArray(product)) {
      throw new PlatformError('cache_invalid_product', 'Cached catalog contains an invalid product record');
    }
    const productId = String(product.product_id ?? product.id ?? '').trim();
    if (!productId) {
      throw new PlatformError('cache_invalid_product', 'Cached catalog product ID is missing');
    }
  }
  return value;
}

function acceptCachedGeneration(value, maxFallbackAgeMs, now = Date.now()) {
''',
)

age_test = "web/test/catalog-cache-fallback-age.test.mjs"
replace_once(
    age_test,
    '''    manifest: {
      generation_id: generationId,
      generated_at: typeof generatedAt === 'number' ? new Date(generatedAt).toISOString() : generatedAt,
    },
''',
    '''    manifest: {
      schema_version: 4,
      generation_id: generationId,
      generated_at: typeof generatedAt === 'number' ? new Date(generatedAt).toISOString() : generatedAt,
      index: { url: 'https://example.test/data/catalog-v4/index.json' },
    },
''',
)

persistence_test = "web/test/catalog-cache-persistence.test.mjs"
replace_once(
    persistence_test,
    '''    manifest: { generation_id: generationId, generated_at: new Date().toISOString() },
''',
    '''    manifest: {
      schema_version: 4,
      generation_id: generationId,
      generated_at: new Date().toISOString(),
      index: { url: 'https://example.test/index.json' },
    },
''',
)
