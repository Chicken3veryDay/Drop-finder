export interface CatalogProductEnvelope {
  variants: unknown[];
  [key: string]: unknown;
}

export interface CatalogIndexEnvelope {
  products: CatalogProductEnvelope[];
  [key: string]: unknown;
}

export interface CatalogGenerationEnvelope {
  generationId: string;
  index: CatalogIndexEnvelope;
  [key: string]: unknown;
}

export interface CatalogGenerationClientOptions {
  cache?: {
    getLastComplete(): Promise<CatalogGenerationEnvelope | null>;
    putComplete(value: CatalogGenerationEnvelope): Promise<void> | void;
  };
  fetchImpl?: typeof fetch;
  maxRetries?: number;
  [key: string]: unknown;
}

export function canonicalizeCatalogIndex<T>(index: T): Promise<T>;
export function canonicalizeCatalogGeneration<T>(generation: T): Promise<T>;

export class CanonicalCatalogGenerationClient {
  constructor(options?: CatalogGenerationClientOptions);
  initialize(options?: { signal?: AbortSignal; force?: boolean }): Promise<CatalogGenerationEnvelope>;
  refresh(options?: { signal?: AbortSignal; allowCachedFallback?: boolean }): Promise<CatalogGenerationEnvelope>;
  snapshot(): CatalogGenerationEnvelope | null;
}
