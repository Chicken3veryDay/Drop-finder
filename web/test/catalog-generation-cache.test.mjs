import test from 'node:test';
import assert from 'node:assert/strict';

import { BrowserGenerationCache } from '../src/platform/catalog/catalog-generation-client.js';

class FakeCache {
  constructor() { this.entries = new Map(); }
  async match(input) { return this.entries.get(String(input))?.clone(); }
  async put(input, response) { this.entries.set(String(input), response.clone()); }
}

class FakeCacheStorage {
  constructor() { this.caches = new Map(); }
  async open(name) {
    if (!this.caches.has(name)) this.caches.set(name, new FakeCache());
    return this.caches.get(name);
  }
}

function generation(id, deploymentUrl) {
  return {
    generationId: id,
    manifest: { generation_id: id },
    index: { generation_id: id, products: [] },
    manifestUrl: new URL('./data/catalog-v4/manifest.json', deploymentUrl).href,
    publicationBaseUrl: deploymentUrl,
    activatedAt: 1,
    source: 'network',
  };
}

test('browser generation fallback is isolated between same-origin deployment paths', async () => {
  const cacheStorage = new FakeCacheStorage();
  const mainUrl = 'https://raw.githack.com/Chicken3veryDay/Drop-finder/main/';
  const productionUrl = 'https://raw.githack.com/Chicken3veryDay/Drop-finder/gh-pages/';
  const main = new BrowserGenerationCache({ cacheStorage, deploymentUrl: mainUrl });
  const production = new BrowserGenerationCache({ cacheStorage, deploymentUrl: productionUrl });

  await main.putComplete(generation('main-generation', mainUrl));
  await production.putComplete(generation('production-generation', productionUrl));

  assert.notEqual(main.key, production.key);
  assert.equal((await main.getLastComplete())?.generationId, 'main-generation');
  assert.equal((await production.getLastComplete())?.generationId, 'production-generation');
});

test('browser generation fallback rejects foreign and legacy cache envelopes', async () => {
  const cacheStorage = new FakeCacheStorage();
  const deploymentUrl = 'https://raw.githack.com/Chicken3veryDay/Drop-finder/gh-pages/';
  const foreignUrl = 'https://raw.githack.com/Chicken3veryDay/Drop-finder/main/';
  const cache = new BrowserGenerationCache({ cacheStorage, deploymentUrl });
  const storage = await cacheStorage.open(cache.cacheName);

  await storage.put(cache.key, new Response(JSON.stringify({
    schemaVersion: 'dropfinder-generation-cache-v2',
    deploymentKey: foreignUrl,
    generation: generation('foreign', foreignUrl),
  })));
  assert.equal(await cache.getLastComplete(), null);

  await storage.put(cache.key, new Response(JSON.stringify(generation('legacy', deploymentUrl))));
  assert.equal(await cache.getLastComplete(), null);

  await cache.putComplete(generation('current', deploymentUrl));
  assert.equal((await cache.getLastComplete())?.generationId, 'current');
});

test('browser generation fallback ignores a generation whose publication base is foreign', async () => {
  const cacheStorage = new FakeCacheStorage();
  const deploymentUrl = 'https://raw.githack.com/Chicken3veryDay/Drop-finder/gh-pages/';
  const cache = new BrowserGenerationCache({ cacheStorage, deploymentUrl });

  await cache.putComplete(generation(
    'foreign',
    'https://raw.githack.com/Chicken3veryDay/Drop-finder/main/',
  ));

  assert.equal(await cache.getLastComplete(), null);
  assert.equal((await cacheStorage.open(cache.cacheName)).entries.size, 0);
});
