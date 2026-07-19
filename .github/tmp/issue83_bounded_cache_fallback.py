from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


source = "web/src/platform/catalog/catalog-generation-client.js"
replace_once(
    source,
    "  staleMs: 5 * 60_000,\n",
    "  staleMs: 5 * 60_000,\n  maxFallbackAgeMs: 30 * 60_000,\n",
)
replace_once(
    source,
    "const CACHE_RECORD_SCHEMA = 'dropfinder-generation-cache-v2';\n",
    "const CACHE_RECORD_SCHEMA = 'dropfinder-generation-cache-v3';\nconst MAX_FUTURE_CACHE_SKEW_MS = 60_000;\n",
)
replace_once(
    source,
    "        const cached = await this.cache.getLastComplete();\n        if (!cached) throw error;\n        return Object.freeze({ ...cached, source: 'cache-fallback' });\n",
    "        const cached = await this.cache.getLastComplete();\n        if (!cached) throw error;\n        const accepted = acceptCachedGeneration(cached, this.options.maxFallbackAgeMs);\n        if (!accepted) {\n          throw new PlatformError(\n            'cache_fallback_stale',\n            'Cached catalog is too old or has invalid freshness metadata',\n            error,\n          );\n        }\n        return Object.freeze({ ...accepted, source: 'cache-fallback' });\n",
)
replace_once(
    source,
    "    this.cacheName = options.cacheName ?? 'dropfinder-client-generation-v2';\n",
    "    this.cacheName = options.cacheName ?? 'dropfinder-client-generation-v3';\n",
)
replace_once(
    source,
    "    this.key = new URL('./__dropfinder__/last-complete-v2.json', this.deploymentUrl).href;\n",
    "    this.key = new URL('./__dropfinder__/last-complete-v3.json', this.deploymentUrl).href;\n",
)
replace_once(
    source,
    "      if (!this.owns(record.generation)) return null;\n      return Object.freeze(record.generation);\n",
    "      if (!this.owns(record.generation)) return null;\n      if (!Number.isFinite(record.cachedAt)) return null;\n      return Object.freeze({ ...record.generation, cachedAt: record.cachedAt });\n",
)
replace_once(
    source,
    "      deploymentKey: this.deploymentKey,\n      generation: value,\n",
    "      deploymentKey: this.deploymentKey,\n      cachedAt: Date.now(),\n      generation: value,\n",
)
replace_once(
    source,
    "export class MemoryGenerationCache {\n  constructor() { this.complete = null; }\n  async getLastComplete() { return this.complete; }\n  async putComplete(value) { this.complete = value; }\n}\n\nfunction createSharedOperation(start, onSettled) {\n",
    "export class MemoryGenerationCache {\n  constructor() { this.complete = null; }\n  async getLastComplete() { return this.complete; }\n  async putComplete(value) {\n    this.complete = Object.freeze({ ...value, cachedAt: Date.now() });\n  }\n}\n\nfunction acceptCachedGeneration(value, maxFallbackAgeMs, now = Date.now()) {\n  const maxAge = Number(maxFallbackAgeMs);\n  if (!Number.isFinite(maxAge) || maxAge < 0) {\n    throw new PlatformError(\n      'invalid_fallback_age',\n      'Maximum cached catalog fallback age must be a nonnegative finite number',\n    );\n  }\n  const cachedAt = Number(value?.cachedAt);\n  const generatedAt = Date.parse(String(\n    value?.manifest?.generated_at ?? value?.manifest?.generatedAt ?? '',\n  ));\n  if (!Number.isFinite(cachedAt) || !Number.isFinite(generatedAt)) return null;\n  if (cachedAt > now + MAX_FUTURE_CACHE_SKEW_MS) return null;\n  if (generatedAt > now + MAX_FUTURE_CACHE_SKEW_MS) return null;\n  const age = now - Math.min(cachedAt, generatedAt);\n  if (!Number.isFinite(age) || age < 0 || age > maxAge) return null;\n  return value;\n}\n\nfunction createSharedOperation(start, onSettled) {\n",
)

replace_once(
    "web/test/platform.test.mjs",
    "  await cache.putComplete({ generationId: 'cached', manifest: {}, index: { products: [] }, activatedAt: 1, source: 'cache' });\n",
    "  await cache.putComplete({\n    generationId: 'cached',\n    manifest: { generated_at: new Date().toISOString() },\n    index: { products: [] },\n    activatedAt: 1,\n    source: 'cache',\n  });\n",
)

persistence = "web/test/catalog-cache-persistence.test.mjs"
replace_once(
    persistence,
    "    generation_id: generationId,\n    index: {\n",
    "    generation_id: generationId,\n    generated_at: new Date().toISOString(),\n    index: {\n",
)
replace_once(
    persistence,
    "    manifest: { generation_id: generationId },\n",
    "    manifest: { generation_id: generationId, generated_at: new Date().toISOString() },\n",
)
replace_once(
    persistence,
    "    activatedAt: 1,\n    source: 'cache',\n",
    "    activatedAt: Date.now(),\n    cachedAt: Date.now(),\n    source: 'cache',\n",
)
