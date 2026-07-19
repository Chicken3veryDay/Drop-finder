from pathlib import Path

path = Path("web/src/platform/catalog/catalog-generation-client.js")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one anchor, found {count}: {old[:100]!r}")
    text = text.replace(old, new, 1)


replace_once(
'''  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  snapshot() {
''',
'''  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(event) {
    for (const listener of this.listeners) listener(event);
  }

  snapshot() {
''')

replace_once(
'''      try {
        const generation = await this.loadCompleteGeneration(controller.signal);
        await this.cache.putComplete(generation);
        return generation;
      } catch (error) {
''',
'''      try {
        const generation = await this.loadCompleteGeneration(controller.signal);
        try {
          await this.cache.putComplete(generation);
        } catch (error) {
          if (controller.signal.aborted || error?.name === 'AbortError') throw abortError();
          this.emit(Object.freeze({
            type: 'generation-cache-degraded',
            generationId: generation.generationId,
            code: cachePersistenceCode(error),
            error,
          }));
        }
        return generation;
      } catch (error) {
''')

replace_once(
'''    this.active = Object.freeze({ ...generation, source });
    for (const listener of this.listeners) listener({ type: 'generation-activated', previous, current: this.active });
  }
''',
'''    this.active = Object.freeze({ ...generation, source });
    this.emit(Object.freeze({ type: 'generation-activated', previous, current: this.active }));
  }
''')

replace_once(
'''function isRetryableFetchError(error) {
''',
'''function cachePersistenceCode(error) {
  if (error?.name === 'QuotaExceededError') return 'cache_quota_exceeded';
  if (error?.name === 'SecurityError') return 'cache_security_denied';
  return 'cache_persistence_failed';
}

function isRetryableFetchError(error) {
''')

path.write_text(text, encoding="utf-8")
