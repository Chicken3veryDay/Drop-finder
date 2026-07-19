import { PlatformError } from '../contracts.js';

const DEFAULTS = Object.freeze({
  estimatedRowHeight: 176,
  overscanPx: 420,
  pageSize: 120,
  maxRetainedPages: 8,
});

/**
 * Headless variable-height virtualization model with a bounded, offset-aware
 * page window. Evicted rows retain estimated scroll space and can be refetched
 * when the viewport approaches the loaded boundary.
 */
export class VirtualMarketplaceAdapter {
  constructor(options = {}) {
    this.options = { ...DEFAULTS, ...options };
    this.items = [];
    this.itemByKey = new Map();
    this.heights = new Map();
    this.offsets = [0];
    this.viewport = { scrollTop: 0, height: 0 };
    this.focusedKey = null;
    this.anchor = null;
    this.resultVersion = null;
    this.totalCount = 0;
    this.loadedPages = new Map();
    this.pageRequests = new Map();
    this.baseOffset = 0;
    this.endOffset = 0;
    this.listeners = new Set();
  }

  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }

  replace({ rows, total, version, queryKey = null, offset = 0, preserveAnchor = false }) {
    this.replacePages({
      pages: [{ offset, rows }],
      total,
      version,
      queryKey,
      preserveAnchor,
    });
  }

  replacePages({ pages, total, version, queryKey = null, preserveAnchor = false }) {
    if (!Array.isArray(pages)) throw new PlatformError('invalid_pages', 'Virtualized pages must be an array');
    if (pages.length > this.options.maxRetainedPages) {
      throw new PlatformError('page_window_oversized', 'Virtualized page window exceeds its retention limit');
    }
    const priorAnchor = preserveAnchor ? this.captureAnchor() : null;
    const normalized = [...pages]
      .map(page => {
        if (!Number.isInteger(page?.offset) || page.offset < 0 || !Array.isArray(page.rows)) {
          throw new PlatformError('invalid_page', 'Virtualized page offset and rows are required');
        }
        return [page.offset, dedupe(page.rows)];
      })
      .sort((left, right) => left[0] - right[0]);

    this.resultVersion = queryKey ?? version;
    this.totalCount = Math.max(0, Number(total) || 0);
    this.loadedPages = new Map(normalized);
    this.baseOffset = normalized[0]?.[0] ?? 0;
    const last = normalized.at(-1);
    this.endOffset = last ? Math.min(this.totalCount, last[0] + last[1].length) : 0;
    this.rebuildItemsFromPages();
    this.rebuildOffsets();

    if (priorAnchor && this.itemByKey.has(priorAnchor.key)) this.restoreAnchor(priorAnchor);
    else if (this.baseOffset === 0) this.viewport.scrollTop = 0;
    if (this.focusedKey && !this.itemByKey.has(this.focusedKey)) this.focusedKey = null;
    this.emit('replace-pages');
  }

  appendPage(offset, rows, identity = this.resultVersion) {
    if (identity !== this.resultVersion) return false;
    if (!Number.isInteger(offset) || offset < 0 || this.loadedPages.has(offset)) return false;
    const pages = new Map(this.loadedPages);
    pages.set(offset, dedupe(rows));
    while (pages.size > this.options.maxRetainedPages) {
      const offsets = [...pages.keys()].sort((left, right) => left - right);
      const viewportRow = Math.floor((this.viewport.scrollTop + (this.viewport.height / 2)) / this.options.estimatedRowHeight);
      const removable = offsets
        .filter(candidate => candidate !== offset)
        .sort((left, right) => Math.abs(right - viewportRow) - Math.abs(left - viewportRow))[0];
      if (removable == null) break;
      pages.delete(removable);
    }
    this.replacePages({
      pages: [...pages].map(([pageOffset, pageRows]) => ({ offset: pageOffset, rows: pageRows })),
      total: this.totalCount,
      version: this.resultVersion,
      queryKey: this.resultVersion,
      preserveAnchor: true,
    });
    this.emit('append');
    return true;
  }

  async requestPage(offset, loader, identity = this.resultVersion) {
    if (identity !== this.resultVersion) return [];
    if (this.loadedPages.has(offset)) return this.loadedPages.get(offset);
    const requestKey = `${identity}:${offset}`;
    if (this.pageRequests.has(requestKey)) return this.pageRequests.get(requestKey);
    const request = Promise.resolve(loader(offset, this.options.pageSize))
      .then(result => {
        if (identity !== this.resultVersion) return [];
        this.appendPage(offset, result.rows, result.queryKey ?? result.version ?? identity);
        return result.rows;
      })
      .finally(() => this.pageRequests.delete(requestKey));
    this.pageRequests.set(requestKey, request);
    return request;
  }

  rebuildItemsFromPages() {
    const merged = [];
    const seen = new Set();
    for (const [pageOffset, page] of [...this.loadedPages].sort((a, b) => a[0] - b[0])) {
      page.forEach((row, pageIndex) => {
        const key = keyOf(row);
        if (seen.has(key)) return;
        seen.add(key);
        merged.push({ row, globalIndex: Number(row?.row?.stableIndex ?? row?.stableIndex ?? (pageOffset + pageIndex)) });
      });
    }
    merged.sort((left, right) => left.globalIndex - right.globalIndex || keyOf(left.row).localeCompare(keyOf(right.row)));
    this.items = merged.map(entry => entry.row);
    this.itemByKey = new Map(merged.map((entry, index) => [keyOf(entry.row), {
      row: entry.row,
      index,
      globalIndex: entry.globalIndex,
    }]));
  }

  setViewport(scrollTop, height) {
    this.viewport = { scrollTop: Math.max(0, scrollTop), height: Math.max(0, height) };
    this.anchor = this.captureAnchor();
    this.emit('viewport');
  }

  measure(key, height) {
    if (!this.itemByKey.has(key) || !Number.isFinite(height) || height <= 0) return false;
    const previous = this.heights.get(key) ?? this.options.estimatedRowHeight;
    if (Math.abs(previous - height) < 0.5) return false;
    const anchor = this.captureAnchor();
    this.heights.set(key, height);
    this.rebuildOffsets();
    this.restoreAnchor(anchor);
    this.emit('measure');
    return true;
  }

  loadedRange() {
    const startPx = this.baseOffset * this.options.estimatedRowHeight;
    const endPx = startPx + (this.offsets.at(-1) ?? 0);
    return Object.freeze({
      startOffset: this.baseOffset,
      endOffset: this.endOffset,
      startPx,
      endPx,
      pageOffsets: Object.freeze([...this.loadedPages.keys()].sort((left, right) => left - right)),
    });
  }

  window() {
    const totalHeight = this.totalHeight();
    const loaded = this.loadedRange();
    if (!this.items.length || this.viewport.height <= 0) {
      return { start: 0, end: 0, items: [], topSpacer: loaded.startPx, bottomSpacer: Math.max(0, totalHeight - loaded.startPx), totalCount: this.totalCount, ariaRowCount: this.totalCount, renderedCount: 0 };
    }
    const localTop = this.viewport.scrollTop - loaded.startPx;
    const localBottom = localTop + this.viewport.height;
    if (localBottom < -this.options.overscanPx || localTop > (this.offsets.at(-1) ?? 0) + this.options.overscanPx) {
      return { start: 0, end: 0, items: [], topSpacer: loaded.startPx, bottomSpacer: Math.max(0, totalHeight - loaded.startPx), totalCount: this.totalCount, ariaRowCount: this.totalCount, renderedCount: 0 };
    }
    const min = Math.max(0, localTop - this.options.overscanPx);
    const max = Math.max(0, localBottom + this.options.overscanPx);
    const start = Math.max(0, upperBound(this.offsets, min) - 1);
    const end = Math.min(this.items.length, upperBound(this.offsets, max));
    return Object.freeze({
      start,
      end,
      items: this.items.slice(start, end),
      topSpacer: loaded.startPx + (this.offsets[start] ?? 0),
      bottomSpacer: Math.max(0, totalHeight - (loaded.startPx + (this.offsets[end] ?? (this.offsets.at(-1) ?? 0)))),
      totalCount: this.totalCount,
      ariaRowCount: this.totalCount,
      renderedCount: end - start,
    });
  }

  focus(key) {
    const entry = this.itemByKey.get(key);
    if (!entry) return null;
    this.focusedKey = key;
    const loaded = this.loadedRange();
    const top = loaded.startPx + this.offsets[entry.index];
    const bottom = loaded.startPx + this.offsets[entry.index + 1];
    if (top < this.viewport.scrollTop) this.viewport.scrollTop = top;
    else if (bottom > this.viewport.scrollTop + this.viewport.height) this.viewport.scrollTop = Math.max(0, bottom - this.viewport.height);
    this.emit('focus');
    return this.viewport.scrollTop;
  }

  captureAnchor() {
    if (!this.items.length) return null;
    const loaded = this.loadedRange();
    const localTop = this.viewport.scrollTop - loaded.startPx;
    if (localTop < 0 || localTop > (this.offsets.at(-1) ?? 0)) return null;
    const index = Math.max(0, Math.min(this.items.length - 1, upperBound(this.offsets, localTop) - 1));
    return { key: keyOf(this.items[index]), delta: localTop - this.offsets[index] };
  }

  restoreAnchor(anchor) {
    if (!anchor) return;
    const entry = this.itemByKey.get(anchor.key);
    if (!entry) return;
    const loaded = this.loadedRange();
    this.viewport.scrollTop = Math.max(0, loaded.startPx + this.offsets[entry.index] + anchor.delta);
    this.anchor = anchor;
  }

  totalHeight() {
    const retainedHeight = this.offsets.at(-1) ?? 0;
    const before = this.baseOffset * this.options.estimatedRowHeight;
    const after = Math.max(0, this.totalCount - this.endOffset) * this.options.estimatedRowHeight;
    return before + retainedHeight + after;
  }

  rebuildOffsets() {
    const offsets = new Array(this.items.length + 1);
    offsets[0] = 0;
    for (let index = 0; index < this.items.length; index += 1) {
      offsets[index + 1] = offsets[index] + (this.heights.get(keyOf(this.items[index])) ?? this.options.estimatedRowHeight);
    }
    this.offsets = offsets;
  }

  emit(reason) {
    const snapshot = { reason, viewport: { ...this.viewport }, window: this.window(), loadedRange: this.loadedRange(), focusedKey: this.focusedKey };
    for (const listener of this.listeners) listener(snapshot);
  }
}

function keyOf(row) {
  const key = row?.productId ?? row?.id;
  if (key == null || key === '') throw new PlatformError('invalid_row_key', 'Virtual row has no stable product identity');
  return String(key);
}

function dedupe(rows) {
  const output = [];
  const seen = new Set();
  for (const row of rows) {
    const key = keyOf(row);
    if (!seen.has(key)) { seen.add(key); output.push(row); }
  }
  return output;
}

function upperBound(values, needle) {
  let low = 0; let high = values.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (values[mid] <= needle) low = mid + 1;
    else high = mid;
  }
  return low;
}
