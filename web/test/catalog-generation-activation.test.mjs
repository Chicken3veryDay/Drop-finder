import test from 'node:test';
import assert from 'node:assert/strict';

import {
  CatalogGenerationClient,
  MemoryGenerationCache,
} from '../src/platform/catalog/catalog-generation-client.js';
import { PwaGenerationCoordinator } from '../src/platform/pwa/pwa-generation-coordinator.js';

const ORIGIN = 'https://app.test';
const MANIFEST_URL = `${ORIGIN}/data/catalog-v4/manifest.json`;
const INDEX_URL = `${ORIGIN}/data/catalog-v4/index.json`;

class FakeWorker {
  constructor() {
    this.messages = [];
    this.onPostMessage = null;
  }

  postMessage(message) {
    this.messages.push(message);
    this.onPostMessage?.(message);
  }
}

class FakeServiceWorkerContainer {
  constructor(worker) {
    this.controller = worker;
    this.listeners = new Set();
    this.registration = {
      waiting: null,
      installing: null,
      addEventListener() {},
    };
  }

  addEventListener(type, listener) {
    if (type === 'message') this.listeners.add(listener);
  }

  removeEventListener(type, listener) {
    if (type === 'message') this.listeners.delete(listener);
  }

  async register() {
    return this.registration;
  }

  emit(data) {
    for (const listener of this.listeners) listener({ data });
  }
}

const waitFor = async predicate => {
  const deadline = Date.now() + 2_000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error('Timed out waiting for test condition');
    await new Promise(resolve => setTimeout(resolve, 5));
  }
};

function catalogFetch(generationId) {
  const manifest = {
    schema_version: 4,
    generation_id: generationId,
    compact_index: { path: 'data/catalog-v4/index.json' },
  };
  const index = {
    generation_id: generationId,
    products: [],
  };
  return async input => {
    const url = String(input);
    if (url === MANIFEST_URL) return json(manifest);
    if (url === INDEX_URL) return json(index);
    return new Response('', { status: 404 });
  };
}

function completeGeneration(generationId) {
  return Object.freeze({
    generationId,
    manifest: {
      schema_version: 4,
      generation_id: generationId,
      compact_index: { path: 'data/catalog-v4/index.json' },
    },
    index: { generation_id: generationId, products: [] },
    manifestUrl: MANIFEST_URL,
    publicationBaseUrl: `${ORIGIN}/`,
    activatedAt: Date.now(),
    source: 'network',
  });
}

test('catalog publication waits for the controlling worker activation acknowledgement', async () => {
  const worker = new FakeWorker();
  const serviceWorker = new FakeServiceWorkerContainer(worker);
  const coordinator = new PwaGenerationCoordinator({ navigator: { serviceWorker } });
  const client = new CatalogGenerationClient({
    manifestUrl: MANIFEST_URL,
    fetchImpl: catalogFetch('g2'),
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
  });

  try {
    const initializing = client.initialize({ force: true });
    await waitFor(() => worker.messages.some(message => message.type === 'activate-generation'));
    assert.equal(client.snapshot(), null);

    serviceWorker.emit({ type: 'generation-active', generationId: 'g2' });
    const generation = await initializing;

    assert.equal(generation.generationId, 'g2');
    assert.equal(client.snapshot()?.generationId, 'g2');
  } finally {
    coordinator.dispose();
  }
});

test('failed worker activation keeps the prior complete catalog visible', async () => {
  const worker = new FakeWorker();
  const serviceWorker = new FakeServiceWorkerContainer(worker);
  const coordinator = new PwaGenerationCoordinator({ navigator: { serviceWorker } });
  const client = new CatalogGenerationClient({
    manifestUrl: MANIFEST_URL,
    fetchImpl: catalogFetch('g2'),
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
  });
  client.activatePrepared(completeGeneration('g1'));
  worker.onPostMessage = message => {
    if (message.type === 'generation-status') {
      queueMicrotask(() => serviceWorker.emit({ type: 'generation-status', id: 'g1' }));
    }
    if (message.type === 'activate-generation') {
      queueMicrotask(() => serviceWorker.emit({
        type: 'generation-error',
        generationId: message.generationId,
        code: 'generation_corrupt',
      }));
    }
  };

  try {
    await assert.rejects(
      client.initialize({ force: true }),
      error => error?.code === 'generation_corrupt',
    );
    assert.equal(client.snapshot()?.generationId, 'g1');
  } finally {
    coordinator.dispose();
  }
});

test('transient incomplete activation is retried within the existing deadline', async () => {
  const worker = new FakeWorker();
  const serviceWorker = new FakeServiceWorkerContainer(worker);
  const coordinator = new PwaGenerationCoordinator({ navigator: { serviceWorker } });
  let attempts = 0;
  worker.onPostMessage = message => {
    if (message.type === 'generation-status') {
      queueMicrotask(() => serviceWorker.emit({ type: 'generation-status', id: 'g1' }));
    }
    if (message.type === 'activate-generation') {
      attempts += 1;
      queueMicrotask(() => serviceWorker.emit(attempts === 1 ? {
        type: 'generation-error',
        generationId: message.generationId,
        code: 'generation_incomplete',
      } : {
        type: 'generation-active',
        generationId: message.generationId,
      }));
    }
  };

  try {
    await coordinator.register();
    const result = await coordinator.activateWhenReady('g2', { timeoutMs: 1_000 });
    assert.deepEqual(result, { status: 'active', generationId: 'g2' });
    assert.equal(attempts, 2);
  } finally {
    coordinator.dispose();
  }
});

test('an already active generation resolves from normalized status without reactivation', async () => {
  const worker = new FakeWorker();
  const serviceWorker = new FakeServiceWorkerContainer(worker);
  const coordinator = new PwaGenerationCoordinator({ navigator: { serviceWorker } });
  worker.onPostMessage = message => {
    if (message.type === 'generation-status') {
      queueMicrotask(() => serviceWorker.emit({ type: 'generation-status', id: 'g2' }));
    }
  };

  try {
    await coordinator.register();
    const result = await coordinator.activateWhenReady('g2', { timeoutMs: 1_000 });
    assert.deepEqual(result, { status: 'active', generationId: 'g2' });
    assert.equal(worker.messages.some(message => message.type === 'activate-generation'), false);
  } finally {
    coordinator.dispose();
  }
});

function json(value) {
  return new Response(JSON.stringify(value), {
    headers: { 'content-type': 'application/json' },
  });
}
