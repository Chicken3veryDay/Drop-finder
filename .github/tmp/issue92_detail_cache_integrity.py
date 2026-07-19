from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


sw = "cloud_pages/sw.js"
replace_once(
    sw,
    "const MAX_DETAIL_ENTRIES = 96;\n",
    "const MAX_DETAIL_ENTRIES = 96;\nconst MAX_DETAIL_BYTES = 2 * 1024 * 1024;\nconst DETAIL_SCHEMA_VERSION = 'dropfinder-product-details-v4';\n",
)
replace_once(
    sw,
    "async function generationDetail(request) {\n"
    "  await restorePromise;\n"
    "  await ensureActiveGeneration();\n"
    "  const generation = request.headers.get('x-dropfinder-generation') || new URL(request.url).searchParams.get('generation');\n"
    "  if (activeGeneration && generation && generation !== activeGeneration.id) return new Response('', { status: 409 });\n"
    "  const cache = activeGeneration ? await caches.open(activeGeneration.cacheName) : null;\n"
    "  const hit = await cache?.match(request, { ignoreSearch: true });\n"
    "  if (hit) return hit;\n"
    "  try {\n"
    "    const response = await fetch(request);\n"
    "    if (!response.ok) return response;\n"
    "    const identity = await readGenerationIdentity(response.clone());\n"
    "    if (activeGeneration && identity.generationId && identity.generationId !== activeGeneration.id) return new Response('', { status: 409 });\n"
    "    if (cache) {\n"
    "      await safeCachePut(cache, request, response.clone());\n"
    "      await trimCache(cache, MAX_DETAIL_ENTRIES, url => isDetailShard(new URL(url).pathname));\n"
    "    }\n"
    "    return response;\n"
    "  } catch {\n"
    "    return hit || new Response('', { status: 503 });\n"
    "  }\n"
    "}\n",
    "async function detailDescriptor(cache, request, generationId) {\n"
    "  const requestUrl = withoutSearch(request.url);\n"
    "  for (const key of await cache.keys()) {\n"
    "    const path = new URL(key.url).pathname;\n"
    "    if (!/(?:catalog-manifest-v4\\.json|\\/catalog-v4\\/manifest\\.json)$/i.test(path)) continue;\n"
    "    const manifestResponse = await cache.match(key);\n"
    "    if (!manifestResponse) continue;\n"
    "    let manifest;\n"
    "    try { manifest = await manifestResponse.json(); } catch { continue; }\n"
    "    if (manifest?.generation_id !== generationId) continue;\n"
    "    const publicationBase = catalogPublicationBase(key.url);\n"
    "    for (const descriptor of manifest.product_detail_shards || []) {\n"
    "      if (!descriptor || !(descriptor.path || descriptor.url)) continue;\n"
    "      const candidate = withoutSearch(new URL(descriptor.path ?? descriptor.url, publicationBase).href);\n"
    "      if (candidate === requestUrl) return descriptor;\n"
    "    }\n"
    "  }\n"
    "  return null;\n"
    "}\n\n"
    "async function inspectDetailResponse(response, descriptor, generationId) {\n"
    "  const contentType = response.headers.get('content-type') || '';\n"
    "  if (!/(?:application|text)\\/(?:[a-z0-9.+-]*\\+)?json/i.test(contentType)) return { valid: false, reason: 'content_type' };\n"
    "  const declared = Number(response.headers.get('content-length'));\n"
    "  if (Number.isFinite(declared) && declared > MAX_DETAIL_BYTES) return { valid: false, reason: 'oversized' };\n"
    "  let bytes;\n"
    "  try { bytes = await response.clone().arrayBuffer(); } catch { return { valid: false, reason: 'body' }; }\n"
    "  if (bytes.byteLength > MAX_DETAIL_BYTES) return { valid: false, reason: 'oversized' };\n"
    "  let payload;\n"
    "  try { payload = await new Response(bytes, { headers: { 'content-type': 'application/json' } }).json(); }\n"
    "  catch { return { valid: false, reason: 'malformed' }; }\n"
    "  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return { valid: false, reason: 'shape' };\n"
    "  if (payload.schema_version !== DETAIL_SCHEMA_VERSION) return { valid: false, reason: 'schema' };\n"
    "  if (payload.generation_id !== generationId) return { valid: false, reason: 'generation', generationId: payload.generation_id };\n"
    "  if (!Array.isArray(payload.products) || !Number.isInteger(payload.product_count)\n"
    "      || payload.product_count !== payload.products.length) return { valid: false, reason: 'count' };\n"
    "  if (!descriptor?.sha256 || !/^[a-f0-9]{64}$/i.test(String(descriptor.sha256))) return { valid: false, reason: 'descriptor' };\n"
    "  let digest;\n"
    "  try { digest = await crypto.subtle.digest('SHA-256', bytes); } catch { return { valid: false, reason: 'hash_unavailable' }; }\n"
    "  const actual = [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('');\n"
    "  if (actual !== String(descriptor.sha256).toLowerCase()) return { valid: false, reason: 'hash' };\n"
    "  return { valid: true, payload };\n"
    "}\n\n"
    "function withoutSearch(value) {\n"
    "  const parsed = new URL(value);\n"
    "  parsed.search = '';\n"
    "  parsed.hash = '';\n"
    "  return parsed.href;\n"
    "}\n\n"
    "async function deleteMatchingEntry(cache, request) {\n"
    "  const target = withoutSearch(request.url);\n"
    "  for (const key of await cache.keys()) {\n"
    "    if (withoutSearch(key.url) === target) await cache.delete(key);\n"
    "  }\n"
    "}\n\n"
    "async function generationDetail(request) {\n"
    "  await restorePromise;\n"
    "  await ensureActiveGeneration();\n"
    "  const requestedGeneration = request.headers.get('x-dropfinder-generation') || new URL(request.url).searchParams.get('generation');\n"
    "  if (activeGeneration && requestedGeneration && requestedGeneration !== activeGeneration.id) return new Response('', { status: 409 });\n"
    "  const cache = activeGeneration ? await caches.open(activeGeneration.cacheName) : null;\n"
    "  const descriptor = cache && activeGeneration ? await detailDescriptor(cache, request, activeGeneration.id) : null;\n"
    "  const hit = await cache?.match(request, { ignoreSearch: true });\n"
    "  if (hit) {\n"
    "    const inspected = descriptor && activeGeneration\n"
    "      ? await inspectDetailResponse(hit.clone(), descriptor, activeGeneration.id)\n"
    "      : { valid: false };\n"
    "    if (inspected.valid) return hit;\n"
    "    await deleteMatchingEntry(cache, request);\n"
    "  }\n"
    "  try {\n"
    "    const response = await fetch(request, { cache: 'no-store' });\n"
    "    if (!response.ok) return response;\n"
    "    if (!cache || !activeGeneration || !descriptor) return response;\n"
    "    const inspected = await inspectDetailResponse(response.clone(), descriptor, activeGeneration.id);\n"
    "    if (!inspected.valid) {\n"
    "      if (inspected.reason === 'generation' && inspected.generationId) return new Response('', { status: 409 });\n"
    "      return response;\n"
    "    }\n"
    "    await safeCachePut(cache, request, response.clone());\n"
    "    await trimCache(cache, MAX_DETAIL_ENTRIES, url => isDetailShard(new URL(url).pathname));\n"
    "    return response;\n"
    "  } catch {\n"
    "    return new Response('', { status: 503 });\n"
    "  }\n"
    "}\n",
)


test_path = "web/test/service-worker.test.mjs"
replace_once(
    test_path,
    "import vm from 'node:vm';\nimport { readFile } from 'node:fs/promises';\n",
    "import vm from 'node:vm';\nimport { createHash, webcrypto } from 'node:crypto';\nimport { readFile } from 'node:fs/promises';\n",
)
replace_once(
    test_path,
    "  const context = vm.createContext({ self, caches, fetch: fetcher, Request, Response, Headers, ReadableStream, URL, DOMException, console, setTimeout, clearTimeout });\n",
    "  const context = vm.createContext({ self, caches, fetch: fetcher, Request, Response, Headers, ReadableStream, URL, DOMException, crypto: webcrypto, console, setTimeout, clearTimeout });\n",
)

append = r'''

const sha256Text = value => createHash('sha256').update(value).digest('hex');

async function activateV4Generation(runtime, generation, detailPath, detailText) {
  const index = JSON.stringify({
    schema_version: 'dropfinder-marketplace-index-v4',
    generation_id: generation,
    product_count: 0,
    in_stock_variant_count: 0,
    products: [],
  });
  const manifest = {
    schema_version: 'dropfinder-catalog-manifest-v4',
    generation_id: generation,
    compact_index: {
      path: 'data/catalog-v4/index.json',
      sha256: sha256Text(index),
    },
    product_detail_shards: [{
      path: detailPath,
      sha256: sha256Text(detailText),
      product_count: 0,
    }],
  };
  runtime.setResponse('data/catalog-v4/index.json', new Response(index, {
    headers: { 'content-type': 'application/json' },
  }));
  runtime.setJson('data/catalog-v4/manifest.json', manifest);
  await runtime.dispatch('fetch', {
    request: new Request(`${BASE}data/catalog-v4/manifest.json`),
  });
  assert.ok(runtime.messages.some(message => message.type === 'generation-active' && message.generationId === generation));
}

function validDetail(generation) {
  return JSON.stringify({
    schema_version: 'dropfinder-product-details-v4',
    generation_id: generation,
    product_count: 0,
    products: [],
  });
}

test('service worker never caches malformed or identity-less detail responses and retries recovered network', async () => {
  for (const [name, badResponse] of [
    ['html', new Response('<!doctype html><title>temporary</title>', { headers: { 'content-type': 'text/html' } })],
    ['malformed', new Response('{bad', { headers: { 'content-type': 'application/json' } })],
    ['identity-less', json({ schema_version: 'dropfinder-product-details-v4', product_count: 0, products: [] })],
    ['wrong-schema', json({ schema_version: 'wrong', generation_id: 'g1', product_count: 0, products: [] })],
    ['generic-error', json({ error: 'temporary' })],
  ]) {
    const runtime = await createRuntime();
    const generation = 'g1';
    const path = 'data/catalog-v4/details/000.json';
    const good = validDetail(generation);
    await activateV4Generation(runtime, generation, path, good);
    const requestPath = `${path}?generation=${generation}`;
    runtime.setResponse(requestPath, badResponse);
    runtime.resetFetches();
    const first = await runtime.dispatch('fetch', { request: new Request(`${BASE}${requestPath}`) });
    assert.equal(first.status, 200, name);
    const generationCacheName = (await runtime.caches.keys()).find(value => value.startsWith('dropfinder-data-v2-'));
    const generationCache = await runtime.caches.open(generationCacheName);
    assert.equal(await generationCache.match(`${BASE}${requestPath}`, { ignoreSearch: true }), undefined, name);

    runtime.setResponse(requestPath, new Response(good, { headers: { 'content-type': 'application/json' } }));
    const recovered = await runtime.dispatch('fetch', { request: new Request(`${BASE}${requestPath}`) });
    assert.equal((await recovered.json()).generation_id, generation, name);
    assert.equal(runtime.fetches.filter(url => url === `${BASE}${requestPath}`).length, 2, name);
    assert.ok(await generationCache.match(`${BASE}${requestPath}`, { ignoreSearch: true }), name);
  }
});

test('service worker rejects wrong-generation and hash-invalid detail responses without poisoning cache', async () => {
  const runtime = await createRuntime();
  const generation = 'g1';
  const path = 'data/catalog-v4/details/000.json';
  const good = validDetail(generation);
  await activateV4Generation(runtime, generation, path, good);
  const requestPath = `${path}?generation=${generation}`;
  const generationCacheName = (await runtime.caches.keys()).find(value => value.startsWith('dropfinder-data-v2-'));
  const generationCache = await runtime.caches.open(generationCacheName);

  runtime.setJson(requestPath, {
    schema_version: 'dropfinder-product-details-v4',
    generation_id: 'g2',
    product_count: 0,
    products: [],
  });
  const wrongGeneration = await runtime.dispatch('fetch', { request: new Request(`${BASE}${requestPath}`) });
  assert.equal(wrongGeneration.status, 409);
  assert.equal(await generationCache.match(`${BASE}${requestPath}`, { ignoreSearch: true }), undefined);

  const hashInvalid = JSON.stringify({
    schema_version: 'dropfinder-product-details-v4',
    generation_id: generation,
    product_count: 1,
    products: [{ product_id: 'unexpected' }],
  });
  runtime.setResponse(requestPath, new Response(hashInvalid, { headers: { 'content-type': 'application/json' } }));
  const invalid = await runtime.dispatch('fetch', { request: new Request(`${BASE}${requestPath}`) });
  assert.equal(invalid.status, 200);
  assert.equal(await generationCache.match(`${BASE}${requestPath}`, { ignoreSearch: true }), undefined);

  runtime.setResponse(requestPath, new Response(good, { headers: { 'content-type': 'application/json' } }));
  const recovered = await runtime.dispatch('fetch', { request: new Request(`${BASE}${requestPath}`) });
  assert.equal((await recovered.json()).generation_id, generation);
  assert.ok(await generationCache.match(`${BASE}${requestPath}`, { ignoreSearch: true }));
});

test('service worker removes a previously poisoned detail hit and preserves validated offline shards', async () => {
  const runtime = await createRuntime();
  const generation = 'g1';
  const path = 'data/catalog-v4/details/000.json';
  const good = validDetail(generation);
  await activateV4Generation(runtime, generation, path, good);
  const requestPath = `${path}?generation=${generation}`;
  const generationCacheName = (await runtime.caches.keys()).find(value => value.startsWith('dropfinder-data-v2-'));
  const generationCache = await runtime.caches.open(generationCacheName);
  await generationCache.put(`${BASE}${requestPath}`, new Response('<html>poisoned</html>', {
    headers: { 'content-type': 'text/html' },
  }));
  runtime.setResponse(requestPath, new Response(good, { headers: { 'content-type': 'application/json' } }));
  runtime.resetFetches();

  const repaired = await runtime.dispatch('fetch', { request: new Request(`${BASE}${requestPath}`) });
  assert.equal((await repaired.json()).generation_id, generation);
  assert.equal(runtime.fetches.filter(url => url === `${BASE}${requestPath}`).length, 1);

  runtime.setOffline(true);
  const offline = await runtime.dispatch('fetch', { request: new Request(`${BASE}${requestPath}`) });
  assert.equal((await offline.json()).generation_id, generation);
});
'''
path = Path(test_path)
text = path.read_text(encoding="utf-8")
if "service worker never caches malformed or identity-less detail responses" in text:
    raise SystemExit("detail integrity tests already present")
path.write_text(text + append, encoding="utf-8")
