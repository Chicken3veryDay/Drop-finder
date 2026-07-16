import { PlatformError, abortError } from '../contracts.js';

const DEFAULT_ACTIVATION_TIMEOUT_MS = 10_000;
let defaultCoordinator = null;

export async function coordinateCatalogGeneration(generationId, options = {}) {
  if (!defaultCoordinator) {
    if (!globalThis.navigator?.serviceWorker?.controller) {
      return Object.freeze({ status: 'uncontrolled', generationId: String(generationId ?? '') });
    }
    throw new PlatformError(
      'service_worker_coordinator_unavailable',
      'The catalog cannot switch generations until service-worker coordination is available',
    );
  }
  return defaultCoordinator.activateWhenReady(generationId, options);
}

/** Typed bridge between the static application and the versioned service worker. */
export class PwaGenerationCoordinator {
  constructor(options = {}) {
    this.navigator = options.navigator ?? globalThis.navigator;
    this.registration = null;
    this.registrationPromise = null;
    this.listeners = new Set();
    this.listening = false;
    this.activeGenerationId = null;
    this.readyGenerationId = null;
    this.messageHandler = event => this.handleMessage(event.data);
    if (!defaultCoordinator) defaultCoordinator = this;
  }

  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }

  async register(scriptUrl = './sw.js', options = { scope: './' }) {
    if (!this.navigator?.serviceWorker) {
      this.emit({ type: 'unsupported', capability: 'service-worker' });
      return null;
    }
    if (!this.listening) {
      this.navigator.serviceWorker.addEventListener('message', this.messageHandler);
      this.listening = true;
    }
    if (!this.registrationPromise) {
      this.registrationPromise = this.navigator.serviceWorker.register(scriptUrl, options)
        .then(registration => {
          this.registration = registration;
          if (registration.waiting) this.requestStatus(registration.waiting);
          this.requestStatus(this.navigator.serviceWorker.controller);
          registration.addEventListener('updatefound', () => {
            const worker = registration.installing;
            worker?.addEventListener('statechange', () => {
              if (worker.state === 'installed' && this.navigator.serviceWorker.controller) {
                this.requestStatus(worker);
              }
            });
          });
          return registration;
        })
        .catch(error => {
          this.registrationPromise = null;
          throw error;
        });
    }
    return this.registrationPromise;
  }

  async activateReadyGeneration(generationId) {
    const worker = this.registration?.waiting ?? this.navigator?.serviceWorker?.controller;
    if (!worker) throw new PlatformError('service_worker_unavailable', 'No service worker can activate a generation');
    worker.postMessage({ type: 'activate-generation', generationId });
  }

  async activateWhenReady(generationId, { signal, timeoutMs = DEFAULT_ACTIVATION_TIMEOUT_MS } = {}) {
    const target = String(generationId ?? '').trim();
    if (!target) throw new PlatformError('generation_missing', 'A catalog generation is required for service-worker activation');
    if (signal?.aborted) throw abortError();

    if (this.navigator?.serviceWorker && !this.registrationPromise) {
      try {
        await this.register();
      } catch (error) {
        if (!this.navigator.serviceWorker.controller) {
          return Object.freeze({ status: 'uncontrolled', generationId: target });
        }
        this.emit(Object.freeze({ type: 'generation-error', generationId: target, code: 'service_worker_registration_failed', error }));
      }
    }

    const worker = this.registration?.waiting ?? this.navigator?.serviceWorker?.controller;
    if (!worker) return Object.freeze({ status: 'uncontrolled', generationId: target });
    if (this.activeGenerationId === target) {
      return Object.freeze({ status: 'active', generationId: target });
    }

    const timeout = Number(timeoutMs);
    if (!Number.isFinite(timeout) || timeout <= 0) {
      throw new PlatformError('activation_timeout_invalid', 'Service-worker activation timeout must be a positive finite number');
    }

    return new Promise((resolve, reject) => {
      let settled = false;
      let activationRequested = false;
      let unsubscribe = () => {};
      let timer = null;
      let activationTimer = null;

      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        if (timer !== null) clearTimeout(timer);
        if (activationTimer !== null) clearTimeout(activationTimer);
        signal?.removeEventListener('abort', onAbort);
        unsubscribe();
        callback(value);
      };
      const fail = (code, message, cause) => finish(
        reject,
        new PlatformError(code, message, cause),
      );
      const requestActivation = () => {
        if (settled || activationRequested) return;
        activationRequested = true;
        try {
          worker.postMessage({ type: 'activate-generation', generationId: target });
        } catch (error) {
          fail('generation_activation_failed', 'Catalog generation activation could not be requested', error);
        }
      };
      const onAbort = () => finish(reject, abortError());
      const onEvent = event => {
        const eventGeneration = String(event?.generationId ?? event?.id ?? '').trim();
        if ((event?.type === 'generation-active' || event?.type === 'generation-status')
          && eventGeneration === target) {
          finish(resolve, Object.freeze({ status: 'active', generationId: target }));
          return;
        }
        if (event?.type === 'generation-ready' && eventGeneration === target) {
          requestActivation();
          return;
        }
        if (event?.type === 'generation-error' && eventGeneration === target) {
          fail(event.code || 'generation_activation_failed', 'Catalog generation activation failed');
        }
      };

      unsubscribe = this.subscribe(onEvent);
      signal?.addEventListener('abort', onAbort, { once: true });
      timer = setTimeout(() => {
        fail('generation_activation_timeout', `Catalog generation ${target} was not activated before the deadline`);
      }, timeout);

      this.requestStatus(worker);
      if (this.activeGenerationId === target) {
        finish(resolve, Object.freeze({ status: 'active', generationId: target }));
        return;
      }
      if (this.readyGenerationId === target) requestActivation();
      else activationTimer = setTimeout(requestActivation, 0);
    });
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
    const generationId = String(message.generationId ?? message.id ?? '').trim() || null;
    const event = Object.freeze(generationId ? { ...message, generationId } : { ...message });
    if ((event.type === 'generation-active' || event.type === 'generation-status') && generationId) {
      this.activeGenerationId = generationId;
      if (this.readyGenerationId === generationId) this.readyGenerationId = null;
    } else if (event.type === 'generation-ready' && generationId) {
      this.readyGenerationId = generationId;
    }
    this.emit(event);
  }

  emit(event) { for (const listener of this.listeners) listener(event); }

  dispose() {
    if (this.listening) this.navigator?.serviceWorker?.removeEventListener('message', this.messageHandler);
    this.listeners.clear();
    this.registration = null;
    this.registrationPromise = null;
    this.listening = false;
    this.activeGenerationId = null;
    this.readyGenerationId = null;
    if (defaultCoordinator === this) defaultCoordinator = null;
  }
}
