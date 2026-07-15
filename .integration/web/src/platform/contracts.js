/**
 * Versioned public contracts for the performance/platform workstream.
 * Runtime validation is intentional: generated static data is untrusted input.
 */
export const PLATFORM_CONTRACT_VERSION = 1;
export const SUPPORTED_CATALOG_SCHEMA = 'dropfinder-catalog-manifest-v4';

export class PlatformError extends Error {
  constructor(code, message, cause) {
    super(message, cause ? { cause } : undefined);
    this.name = 'PlatformError';
    this.code = code;
  }
}

export function assertNonEmptyString(value, field) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new PlatformError('invalid_contract', `${field} must be a non-empty string`);
  }
  return value;
}

export function assertGenerationEnvelope(value, expectedSchema = null) {
  if (!value || typeof value !== 'object') {
    throw new PlatformError('invalid_manifest', 'Catalog manifest is not an object');
  }
  const supported = value.schema_version === SUPPORTED_CATALOG_SCHEMA || value.schema_version === 4;
  if (!supported || (expectedSchema != null && value.schema_version !== expectedSchema)) {
    throw new PlatformError('unsupported_schema', `Unsupported catalog schema ${String(value.schema_version)}`);
  }
  assertNonEmptyString(value.generation_id, 'generation_id');
  const descriptor = value.compact_index ?? value.index;
  if (!descriptor || typeof descriptor !== 'object') {
    throw new PlatformError('invalid_manifest', 'Catalog manifest is missing compact index metadata');
  }
  assertNonEmptyString(descriptor.path ?? descriptor.url, 'compact index path');
  return value;
}

export function stableCompare(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

export function abortError() {
  return new DOMException('The operation was aborted', 'AbortError');
}
