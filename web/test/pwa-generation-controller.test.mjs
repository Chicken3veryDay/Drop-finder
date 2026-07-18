import test from 'node:test';
import assert from 'node:assert/strict';

import { PwaGenerationCoordinator } from '../src/platform/pwa/pwa-generation-coordinator.js';

class Worker {
  constructor() { this.messages = []; this.onPostMessage = null; }
  postMessage(message) { this.messages.push(message); this.onPostMessage?.(message); }
}

test('generation activation targets the worker controlling current fetches, not a waiting code update', async () => {
  const controller = new Worker();
  const waiting = new Worker();
  const listeners = new Set();
  const serviceWorker = {
    controller,
    addEventListener(type, listener) { if (type === 'message') listeners.add(listener); },
    removeEventListener(type, listener) { if (type === 'message') listeners.delete(listener); },
    async register() {
      return {
        waiting,
        installing: null,
        addEventListener() {},
      };
    },
  };
  const emit = data => { for (const listener of listeners) listener({ data }); };
  controller.onPostMessage = message => {
    if (message.type === 'generation-status') {
      queueMicrotask(() => emit({ type: 'generation-status', id: 'g1' }));
    }
    if (message.type === 'activate-generation') {
      queueMicrotask(() => emit({ type: 'generation-active', generationId: message.generationId }));
    }
  };
  const coordinator = new PwaGenerationCoordinator({ navigator: { serviceWorker } });

  try {
    const result = await coordinator.activateWhenReady('g2', { timeoutMs: 1_000 });
    assert.deepEqual(result, { status: 'active', generationId: 'g2' });
    assert.ok(controller.messages.some(message => message.type === 'activate-generation' && message.generationId === 'g2'));
    assert.equal(waiting.messages.some(message => message.type === 'activate-generation'), false);
  } finally {
    coordinator.dispose();
  }
});
