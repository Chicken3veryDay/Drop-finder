from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


sw = "cloud_pages/sw.js"
replace_once(
    sw,
    "  const url = new URL(event.request.url);\n  if (url.origin !== self.location.origin) {",
    "  const url = new URL(event.request.url);\n  if (isDevelopmentModule(url.pathname)) return;\n  if (url.origin !== self.location.origin) {",
)
replace_once(
    sw,
    "function isHashedAsset(path) { return /\\/assets\\/(?:[^/]+\\/)*[^/]+-[a-z0-9_-]{8}\\.[a-z0-9]+$/i.test(path); }",
    "function isDevelopmentModule(path) { return /^(?:\\/@vite(?:\\/|$)|\\/@react-refresh(?:$|\\?)|\\/@fs\\/|\\/src\\/|\\/node_modules\\/)/.test(path); }\nfunction isHashedAsset(path) { return /\\/assets\\/(?:[^/]+\\/)*[^/]+-[a-z0-9_-]{8}\\.[a-z0-9]+$/i.test(path); }",
)
replace_once(
    sw,
    "async function cacheFirst(request, cacheName) { const cache = await caches.open(cacheName); const hit = await cache.match(request, { ignoreSearch: true }); if (hit) return hit; const response = await fetch(request); if (response.ok) await safeCachePut(cache, request, response.clone()); return response; }",
    "async function cacheFirst(request, cacheName) { const cache = await caches.open(cacheName); const hit = await cache.match(request); if (hit) return hit; const response = await fetch(request); if (response.ok) await safeCachePut(cache, request, response.clone()); return response; }",
)
replace_once(
    sw,
    "async function staleWhileRevalidate(request, cacheName) { const cache = await caches.open(cacheName); const hit = await cache.match(request, { ignoreSearch: true }); const network = fetch(request).then(response => { if (response.ok) safeCachePut(cache, request, response.clone()); return response; }).catch(() => null); if (hit) { void network; return hit; } return (await network) || new Response('', { status: 503 }); }",
    "async function staleWhileRevalidate(request, cacheName) { const cache = await caches.open(cacheName); const hit = await cache.match(request); const network = fetch(request).then(response => { if (response.ok) safeCachePut(cache, request, response.clone()); return response; }).catch(() => null); if (hit) { void network; return hit; } return (await network) || new Response('', { status: 503 }); }",
)

test_path = "web/test/service-worker.test.mjs"
replace_once(
    test_path,
    "function navigationRequest(path) {\n",
    """test('service worker leaves Vite and source modules to the development server', async () => {
  const runtime = await createRuntime();
  for (const path of [
    '/@vite/client',
    '/@react-refresh',
    '/@fs/tmp/source.js',
    '/src/main.tsx',
    '/node_modules/example/index.js?v=one',
  ]) {
    runtime.resetFetches();
    const handled = await runtime.dispatch('fetch', { request: new Request(`${ORIGIN}${path}`) });
    assert.equal(handled, undefined, path);
    assert.deepEqual(runtime.fetches, [], path);
  }
});

test('application cache keeps query-versioned module identities distinct', async () => {
  const runtime = await createRuntime();
  const firstUrl = `${BASE}module.js?v=one`;
  const secondUrl = `${BASE}module.js?v=two`;
  runtime.setResponse(firstUrl, new Response('export default \"one\"', { headers: { 'content-type': 'text/javascript' } }));
  runtime.setResponse(secondUrl, new Response('export default \"two\"', { headers: { 'content-type': 'text/javascript' } }));

  const first = await runtime.dispatch('fetch', { request: new Request(firstUrl) });
  assert.equal(await first.text(), 'export default \"one\"');
  const second = await runtime.dispatch('fetch', { request: new Request(secondUrl) });
  assert.equal(await second.text(), 'export default \"two\"');

  const appCacheName = (await runtime.caches.keys()).find(name => name.startsWith('dropfinder-app-'));
  assert.ok(appCacheName);
  const appCache = await runtime.caches.open(appCacheName);
  assert.equal(await (await appCache.match(firstUrl)).text(), 'export default \"one\"');
  assert.equal(await (await appCache.match(secondUrl)).text(), 'export default \"two\"');
});

function navigationRequest(path) {
""",
)
