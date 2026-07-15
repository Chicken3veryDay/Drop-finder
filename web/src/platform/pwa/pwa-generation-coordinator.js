import { PlatformError } from '../contracts.js';

/** Typed bridge between the static application and the versioned service worker. */
export class PwaGenerationCoordinator {
  constructor(options = {}) {
    this.navigator = options.navigator ?? globalThis.navigator;
    this.registration = null;
    this.listeners = new Set();
    this.messageHandler = event => this.handleMessage(event.data);
  }

  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }

  async register(scriptUrl = './sw.js', options = { scope: './' }) {
    if (!this.navigator?.serviceWorker) {
      this.emit({ type: 'unsupported', capability: 'service-worker' });
      return null;
    }
    this.registration = await this.navigator.serviceWorker.register(scriptUrl, options);
    this.navigator.serviceWorker.addEventListener('message', this.messageHandler);
    if (this.registration.waiting) this.requestStatus(this.registration.waiting);
    this.registration.addEventListener('updatefound', () => {
      const worker = this.registration.installing;
      worker?.addEventListener('statechange', () => {
        if (worker.state === 'installed' && this.navigator.serviceWorker.controller) {
          this.requestStatus(worker);
        }
      });
    });
    return this.registration;
  }

  async activateReadyGeneration(generationId) {
    const worker = this.registration?.waiting ?? this.navigator?.serviceWorker?.controller;
    if (!worker) throw new PlatformError('service_worker_unavailable', 'No service worker can activate a generation');
    worker.postMessage({ type: 'activate-generation', generationId });
  }

  async cacheOpenedDocument(document) {
    const worker = this.navigator?.serviceWorker?.controller;
    if (!worker) return false;
    worker.postMessage({ type: 'cache-document', document });
    return true;
  }

  requestStatus(worker = this.navigator?.serviceWorker?.controller) {
    worker?.postMessage({ type: 'generation-status' });
  }

  handleMessage(message) {
    const allowed = new Set(['generation-ready', 'generation-active', 'generation-error', 'cache-quota', 'generation-status']);
    if (!message || !allowed.has(message.type)) return;
    this.emit(Object.freeze({ ...message }));
  }

  emit(event) { for (const listener of this.listeners) listener(event); }

  dispose() {
    this.navigator?.serviceWorker?.removeEventListener('message', this.messageHandler);
    this.listeners.clear();
    this.registration = null;
  }
}
