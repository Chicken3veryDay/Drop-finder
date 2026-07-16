import test from 'node:test';
import assert from 'node:assert/strict';
import { CatalogGenerationClient, MemoryGenerationCache } from '../src/platform/catalog/catalog-generation-client.js';

function fixtureGeneration(generationId, detail) {
  return {
    generationId,
    manifest: {
      schema_version: 4,
      generation_id: generationId,
      details: {
        p0: {
          url: `https://example.test/${generationId}/p0.json`,
          bytes: detail.length,
        },
      },
    },
    index: {
      generation_id: generationId,
      products: [{ id: 'p0' }],
    },
    manifestUrl: `https://example.test/${generationId}/manifest.json`,
    publicationBaseUrl: `https://example.test/${generationId}/`,
    activatedAt: Date.now(),
    source: 'fixture',
  };
}

test('catalog client rejects detail work that finishes after a newer generation activates', async () => {
  const g1Detail = JSON.stringify({
    generation_id: 'g1',
    product: { id: 'p0', image_url: 'https://example.test/g1.jpg' },
  });
  const g2Detail = JSON.stringify({
    generation_id: 'g2',
    product: { id: 'p0', image_url: 'https://example.test/g2.jpg' },
  });
  const client = new CatalogGenerationClient({
    fetchImpl: async () => new Response('', { status: 500 }),
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
  });
  client.activate(fixtureGeneration('g1', g1Detail), 'fixture');

  let releaseText;
  let markTextStarted;
  const textStarted = new Promise(resolve => {
    markTextStarted = resolve;
  });
  client.fetchDeduped = async () => ({
    text: () => new Promise(resolve => {
      releaseText = () => resolve(g1Detail);
      markTextStarted();
    }),
  });

  const pending = client.loadDetail('p0');
  await textStarted;
  client.activate(fixtureGeneration('g2', g2Detail), 'fixture');
  releaseText();

  await assert.rejects(pending, error => error?.name === 'AbortError');
  assert.equal(client.snapshot().generationId, 'g2');
  assert.equal(client.detailLru.size, 0);
});
