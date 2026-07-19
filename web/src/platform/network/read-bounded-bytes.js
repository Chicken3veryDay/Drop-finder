import { abortError } from '../contracts.js';

export async function readBoundedBytes(response, {
  maxBytes,
  signal,
  oversizedError = () => new RangeError('Response exceeds its byte limit'),
} = {}) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 0) {
    throw new TypeError('maxBytes must be a nonnegative safe integer');
  }
  if (signal?.aborted) throw abortError();

  const contentLength = response.headers?.get?.('content-length');
  const declared = contentLength === null || contentLength === undefined
    ? null
    : Number(contentLength);
  if (Number.isFinite(declared) && declared > maxBytes) {
    await cancelBody(response.body, 'Response exceeds its byte limit');
    throw oversizedError();
  }
  if (!response.body) return new Uint8Array(0);

  const reader = response.body.getReader();
  const chunks = [];
  let totalBytes = 0;
  const onAbort = () => { void cancelReader(reader, signal?.reason); };
  signal?.addEventListener('abort', onAbort, { once: true });

  try {
    while (true) {
      if (signal?.aborted) throw abortError();
      const { done, value } = await reader.read();
      if (signal?.aborted) throw abortError();
      if (done) break;
      const chunk = value instanceof Uint8Array ? value : new Uint8Array(value);
      if (totalBytes + chunk.byteLength > maxBytes) {
        await cancelReader(reader, 'Response exceeds its byte limit');
        throw oversizedError();
      }
      chunks.push(chunk);
      totalBytes += chunk.byteLength;
    }
  } catch (error) {
    if (signal?.aborted || error?.name === 'AbortError') {
      await cancelReader(reader, signal?.reason);
      throw abortError();
    }
    throw error;
  } finally {
    signal?.removeEventListener('abort', onAbort);
    try { reader.releaseLock(); } catch { /* stream already released */ }
  }

  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

async function cancelBody(body, reason) {
  if (!body) return;
  try { await body.cancel(reason); } catch { /* best-effort transport cleanup */ }
}

async function cancelReader(reader, reason) {
  try { await reader.cancel(reason); } catch { /* best-effort transport cleanup */ }
}
