#!/usr/bin/env python3
"""Install staged integration payloads and patch the audited sibling seams."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
STAGED = ROOT / ".integration"


def replace(path: Path, old: str, new: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected integration seam missing in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    left = text.find(start)
    right = text.find(end, left + len(start))
    if left < 0 or right < 0:
        raise RuntimeError(f"Replacement boundaries missing in {path}: {start!r} / {end!r}")
    path.write_text(text[:left] + replacement + text[right:], encoding="utf-8")


def copy_payloads() -> None:
    source_web = STAGED / "web"
    for source in source_web.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(source_web)
        target = WEB / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    source_workflows = STAGED / ".github" / "workflows"
    if source_workflows.exists():
        for source in source_workflows.glob("*.yml"):
            target = ROOT / ".github" / "workflows" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    obsolete = WEB / "vite.config.mjs"
    if obsolete.exists():
        obsolete.unlink()


def patch_registry() -> None:
    path = WEB / "src/app/featureRegistryCore.ts"
    replace(
        path,
        '''    const suppliedProps = isRecord(supplied) ? supplied : {};
    const products = Array.isArray(suppliedProps.products) ? suppliedProps.products : [];
    return createElement(Mount, { ...suppliedProps, products, capabilities });''',
        '''    const suppliedProps = isRecord(supplied) ? supplied : {};
    const Provider = suppliedProps.Provider;
    if (isComponent(Provider)) {
      return createElement(
        Provider as ComponentType<{
          mount: typeof Mount;
          capabilities: MarketplaceRootSlotProps["capabilities"];
        }>,
        { mount: Mount, capabilities },
      );
    }
    const products = Array.isArray(suppliedProps.products) ? suppliedProps.products : [];
    return createElement(Mount, { ...suppliedProps, products, capabilities });''',
    )


def patch_marketplace_contract() -> None:
    path = WEB / "src/features/marketplace/marketplace-core.ts"
    text = path.read_text(encoding="utf-8")
    if not text.startswith("import type { ReactNode } from \"react\";"):
        path.write_text('import type { ReactNode } from "react";\n\n' + text, encoding="utf-8")
    replace(
        path,
        '''export interface MarketplaceQueryCapability {
  query(
    products: readonly MarketplaceProduct[],
    filters: MarketplaceFilters,
    sort: SortOption,
  ): MarketplaceQueryResult;
}

export interface VirtualMarketplaceAdapterProps {''',
        '''export interface MarketplaceQueryCapability {
  query(
    products: readonly MarketplaceProduct[],
    filters: MarketplaceFilters,
    sort: SortOption,
  ): MarketplaceQueryResult;
}

export interface MarketplaceAsyncQueryPage extends MarketplaceQueryResult {
  nextOffset: number | null;
}

export interface MarketplaceAsyncQueryOptions {
  offset: number;
  limit: number;
  expandedProductId: string | null;
  signal?: AbortSignal;
}

export interface MarketplaceAsyncQueryCapability {
  query(
    products: readonly MarketplaceProduct[],
    filters: MarketplaceFilters,
    sort: SortOption,
    options: MarketplaceAsyncQueryOptions,
  ): Promise<MarketplaceAsyncQueryPage>;
}

export interface VirtualMarketplaceAdapterProps {''',
    )
    replace(
        path,
        '''  rows: readonly MarketplaceRowProjection[];
  expandedProductId: string | null;
  renderRow(row: MarketplaceRowProjection): unknown;
  renderExpanded(row: MarketplaceRowProjection): unknown;''',
        '''  rows: readonly MarketplaceRowProjection[];
  total: number;
  expandedProductId: string | null;
  renderRow(row: MarketplaceRowProjection): ReactNode;
  renderExpanded(row: MarketplaceRowProjection): ReactNode;''',
    )
    replace(path, "  render(props: VirtualMarketplaceAdapterProps): unknown;", "  render(props: VirtualMarketplaceAdapterProps): ReactNode;")
    replace(
        path,
        '''  queryEngine?: MarketplaceQueryCapability | undefined;
  virtualization?: VirtualMarketplaceAdapter | undefined;''',
        '''  queryEngine?: MarketplaceQueryCapability | undefined;
  asyncQueryEngine?: MarketplaceAsyncQueryCapability | undefined;
  virtualization?: VirtualMarketplaceAdapter | undefined;''',
    )


def patch_marketplace_component() -> None:
    path = WEB / "src/features/marketplace/MarketplaceFeature.tsx"
    replace(
        path,
        'import { useEffect, useId, useMemo, useRef, useState } from "react";',
        'import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";',
    )
    replace(path, "  queryEngine,\n  virtualization,", "  queryEngine,\n  asyncQueryEngine,\n  virtualization,")
    replace(
        path,
        '''  const query = useMemo(
    () => queryEngine?.query(products, filters, sort) ?? queryMarketplace(products, filters, sort),
    [products, filters, sort, queryEngine],
  );
  const vendors = useMemo(() => uniqueVendors(products), [products]);''',
        '''  const syncQuery = useMemo(
    () => queryEngine?.query(products, filters, sort) ?? queryMarketplace(products, filters, sort),
    [products, filters, sort, queryEngine],
  );
  const [asyncQuery, setAsyncQuery] = useState({
    rows: [] as readonly MarketplaceRowProjection[],
    total: 0,
    nextOffset: null as number | null,
  });
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const loadMorePending = useRef(false);
  const queryRevision = useRef(0);
  const query = asyncQueryEngine ? asyncQuery : syncQuery;
  const vendors = useMemo(() => uniqueVendors(products), [products]);

  useEffect(() => {
    if (!asyncQueryEngine) return;
    const revision = ++queryRevision.current;
    const controller = new AbortController();
    setQueryLoading(true);
    setQueryError(null);
    void asyncQueryEngine.query(products, filters, sort, {
      offset: 0,
      limit: 120,
      expandedProductId,
      signal: controller.signal,
    }).then((result) => {
      if (revision === queryRevision.current && !controller.signal.aborted) setAsyncQuery(result);
    }).catch((caught: unknown) => {
      if (
        revision === queryRevision.current &&
        !controller.signal.aborted &&
        !(caught instanceof DOMException && caught.name === "AbortError")
      ) {
        setQueryError(caught instanceof Error ? caught.message : "Marketplace query failed.");
      }
    }).finally(() => {
      if (revision === queryRevision.current && !controller.signal.aborted) setQueryLoading(false);
    });
    return () => controller.abort();
  }, [asyncQueryEngine, products, filters, sort]);

  const loadMore = useCallback(() => {
    if (!asyncQueryEngine || asyncQuery.nextOffset === null || loadMorePending.current) return;
    loadMorePending.current = true;
    const offset = asyncQuery.nextOffset;
    void asyncQueryEngine.query(products, filters, sort, {
      offset,
      limit: 120,
      expandedProductId,
    }).then((result) => {
      setAsyncQuery((current) => ({
        rows: [...current.rows, ...result.rows],
        total: result.total,
        nextOffset: result.nextOffset,
      }));
    }).catch((caught: unknown) => {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setQueryError(caught instanceof Error ? caught.message : "Additional results could not be loaded.");
      }
    }).finally(() => {
      loadMorePending.current = false;
    });
  }, [asyncQuery, asyncQueryEngine, expandedProductId, filters, products, sort]);

  const effectiveLoading = loading || queryLoading;
  const effectiveError = error || queryError;''',
    )
    text = path.read_text(encoding="utf-8")
    text = text.replace("loading && query.rows.length === 0", "effectiveLoading && query.rows.length === 0")
    text = text.replace("error && query.rows.length === 0", "effectiveError && query.rows.length === 0")
    text = text.replace("<p>{error}</p>", "<p>{effectiveError}</p>")
    text = text.replace("!loading && !error && query.rows.length === 0", "!effectiveLoading && !effectiveError && query.rows.length === 0")
    old = '''                rows: query.rows,
                expandedProductId,
                renderRow,
                renderExpanded: renderRow,
              })'''
    new = '''                rows: query.rows,
                total: query.total,
                expandedProductId,
                renderRow,
                renderExpanded: renderRow,
                onEndReached: loadMore,
              })'''
    if old not in text:
        raise RuntimeError("Virtual marketplace invocation seam missing")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_provider() -> None:
    path = WEB / "src/features/integration/register-marketplace-props.tsx"
    text = path.read_text(encoding="utf-8")
    text = "/* eslint-disable react-refresh/only-export-components */\n" + text
    text = text.replace(
        "const details = Array.isArray(product.variants) ? product.variants.map(objectValue).filter(Boolean) : [];",
        '''const details = Array.isArray(product.variants)
    ? product.variants.map(objectValue).filter((value): value is Record<string, unknown> => value !== null)
    : [];''',
    )
    path.write_text(text, encoding="utf-8")


CATALOG_METHODS = '''  async loadCompleteGeneration(signal) {
    const manifestResponse = await this.fetchBounded(this.options.manifestUrl, {
      signal,
      maxBytes: 512 * 1024,
      cache: 'no-store',
    });
    const manifest = assertGenerationEnvelope(await manifestResponse.json(), this.options.schemaVersion);
    const manifestUrl = manifestResponse.url || new URL(this.options.manifestUrl, locationHref()).href;
    const publicationBaseUrl = publicationBase(manifestUrl);
    const descriptor = manifest.compact_index ?? manifest.index;
    const indexUrl = resolvePublicationUrl(descriptor.path ?? descriptor.url, manifestUrl, publicationBaseUrl);
    const indexResponse = await this.fetchBounded(indexUrl, {
      signal,
      maxBytes: Math.min(descriptor.bytes ?? this.options.maxIndexBytes, this.options.maxIndexBytes),
      cache: 'no-store',
    });
    const indexText = await indexResponse.text();
    await verifyHash(indexText, descriptor.sha256);
    let index;
    try { index = JSON.parse(indexText); }
    catch (cause) { throw new PlatformError('malformed_index', 'Catalog index is malformed', cause); }
    if (index.generation_id !== manifest.generation_id) {
      throw new PlatformError('generation_mismatch', 'Manifest and index generations do not match');
    }
    if (!Array.isArray(index.products)) {
      throw new PlatformError('invalid_index', 'Catalog index products are missing');
    }
    return Object.freeze({
      generationId: manifest.generation_id,
      manifest,
      index,
      manifestUrl,
      publicationBaseUrl,
      activatedAt: Date.now(),
      source: 'network',
    });
  }

  async loadDetail(productId, { signal, prefetch = false } = {}) {
    const generation = this.active;
    if (!generation) throw new PlatformError('not_initialized', 'Catalog generation is not initialized');
    const legacy = generation.manifest.details?.[productId] ?? generation.index.detail_shards?.[productId];
    const product = generation.index.products.find(row => String(row.product_id ?? row.id ?? '') === String(productId));
    const shard = Number(product?.detail_shard);
    const shardName = Number.isInteger(shard) ? `${String(shard).padStart(3, '0')}.json` : null;
    const catalog = shardName
      ? generation.manifest.product_detail_shards?.find(row => String(row.path ?? row.url ?? '').endsWith(`/${shardName}`))
      : null;
    const descriptor = legacy ?? catalog;
    if (!descriptor) throw new PlatformError('detail_missing', 'Product details are unavailable');
    const detailUrl = resolvePublicationUrl(
      descriptor.url ?? descriptor.path,
      generation.manifestUrl ?? locationHref(),
      generation.publicationBaseUrl ?? locationHref(),
    );
    const cacheKey = `${generation.generationId}:${detailUrl}`;
    if (this.detailLru.has(cacheKey)) {
      const hit = this.detailLru.get(cacheKey);
      this.detailLru.delete(cacheKey);
      this.detailLru.set(cacheKey, hit);
      return hit;
    }
    const response = await this.fetchDeduped(cacheKey, detailUrl, {
      signal,
      maxBytes: Math.min(descriptor.bytes ?? this.options.maxDetailBytes, this.options.maxDetailBytes),
      cache: prefetch ? 'force-cache' : 'default',
    });
    const text = await response.text();
    await verifyHash(text, descriptor.sha256);
    let detail;
    try { detail = JSON.parse(text); }
    catch (cause) { throw new PlatformError('malformed_detail', 'Product detail data is malformed', cause); }
    if (detail.generation_id !== generation.generationId) {
      throw new PlatformError('generation_mismatch', 'Detail data belongs to another generation');
    }
    this.detailLru.set(cacheKey, detail);
    while (this.detailLru.size > this.options.maxDetailShards) {
      this.detailLru.delete(this.detailLru.keys().next().value);
    }
    return detail;
  }

'''

CATALOG_HELPERS = '''
function publicationBase(manifestUrl) {
  try {
    const parsed = new URL(manifestUrl, locationHref());
    const marker = '/data/catalog-v4/';
    const index = parsed.pathname.lastIndexOf(marker);
    if (index >= 0) {
      parsed.pathname = parsed.pathname.slice(0, index + 1);
      parsed.search = '';
      parsed.hash = '';
      return parsed.href;
    }
    return new URL('./', parsed).href;
  } catch {
    return locationHref();
  }
}

function resolvePublicationUrl(value, manifestUrl, publicationBaseUrl) {
  const path = String(value ?? '');
  if (/^https?:\/\//i.test(path)) return path;
  if (path.startsWith('./') || path.startsWith('../')) return new URL(path, manifestUrl).href;
  return new URL(path, publicationBaseUrl).href;
}

'''


def patch_catalog_client() -> None:
    path = WEB / "src/platform/catalog/catalog-generation-client.js"
    replace(
        path,
        "  manifestUrl: './data/catalog-manifest-v4.json',\n  schemaVersion: 4,",
        "  manifestUrl: './data/catalog-v4/manifest.json',\n  schemaVersion: null,",
    )
    replace_between(path, "  async loadCompleteGeneration(signal) {", "  cancelObsolete(", CATALOG_METHODS)
    text = path.read_text(encoding="utf-8")
    marker = "\nfunction locationHref()"
    if marker not in text:
        raise RuntimeError("Catalog helper insertion point missing")
    path.write_text(text.replace(marker, CATALOG_HELPERS + marker, 1), encoding="utf-8")


def main() -> None:
    copy_payloads()
    patch_registry()
    patch_marketplace_contract()
    patch_marketplace_component()
    patch_provider()
    patch_catalog_client()
    shutil.rmtree(STAGED)


if __name__ == "__main__":
    main()
