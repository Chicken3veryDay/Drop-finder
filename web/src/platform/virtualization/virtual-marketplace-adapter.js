import { PlatformError } from '../contracts.js';

const DEFAULTS = Object.freeze({
  estimatedRowHeight: 176,
  overscanPx: 420,
  pageSize: 120,
  maxRetainedPages: 8,
});

/**
 * Headless variable-height virtualization model. A shell may bind this to
 * React Virtuoso or a native absolute-positioned list without changing issue
 * #8's feature contract.
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
    this.listeners = new Set();
  }

  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }

  replace({ rows, total, version, queryKey = null, preserveAnchor = false }) {
    if (!Array.isArray(rows)) throw new PlatformError('invalid_rows', 'Virtualized rows must be an array');
    const priorAnchor = preserveAnchor ? this.captureAnchor() : null;
    this.resultVersion = queryKey ?? version;
    this.totalCount = Math.max(rows.length, Number(total) || 0);
    this.items = dedupe(rows);
    this.itemByKey = new Map(this.items.map((row, index) => [keyOf(row), { row, index }]));
    this.loadedPages.clear();
    this.loadedPages.set(0, this.items);
    this.rebuildOffsets();
    if (priorAnchor && this.itemByKey.has(priorAnchor.key)) this.restoreAnchor(priorAnchor);
    else this.viewport.scrollTop = 0;
    if (this.focusedKey && !this.itemByKey.has(this.focusedKey)) this.focusedKey = null;
    this.emit('replace');
  }

  appendPage(offset, rows, identity = this.resultVersion) {
    if (identity !== this.resultVersion) return false;
    if (this.loadedPages.has(offset)) return false;
    const priorAnchor = this.captureAnchor();
    this.loadedPages.set(offset, dedupe(rows));
    while (this.loadedPages.size > this.options.maxRetainedPages) {
      const removable = [...this.loadedPages.keys()].find(pageOffset => pageOffset !== 0 && pageOffset !== offset);
      if (removable == null) break;
      this.loadedPages.delete(removable);
    }
    this.rebuildItemsFromPages();
    this.rebuildOffsets();
    this.restoreAnchor(priorAnchor);
    this.emit('append');
    return true;
  }

  async requestPage(offset, loader) {
    if (this.loadedPages.has(offset)) return this.loadedPages.get(offset);
    if (this.pageRequests.has(offset)) return this.pageRequests.get(offset);
    const request = Promise.resolve(loader(offset, this.options.pageSize))
      .then(result => {
        this.appendPage(offset, result.rows, result.queryKey ?? result.version);
        return result.rows;
      })
      .finally(() => this.pageRequests.delete(offset));
    this.pageRequests.set(offset, request);
    return request;
  }


  rebuildItemsFromPages() {
    const merged = [];
    const seen = new Set();
    for (const [, page] of [...this.loadedPages].sort((a, b) => a[0] - b[0])) {
      for (const row of page) {
        const key = keyOf(row);
        if (!seen.has(key)) { seen.add(key); merged.push(row); }
      }
    }
    this.items = merged;
    this.itemByKey = new Map(this.items.map((row, index) => [keyOf(row), { row, index }]));
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

  window() {
    if (!this.items.length || this.viewport.height <= 0) {
      return { start: 0, end: 0, items: [], topSpacer: 0, bottomSpacer: this.totalHeight(), totalCount: this.totalCount };
    }
    const min = Math.max(0, this.viewport.scrollTop - this.options.overscanPx);
    const max = this.viewport.scrollTop + this.viewport.height + this.options.overscanPx;
    const start = Math.max(0, upperBound(this.offsets, min) - 1);
    const end = Math.min(this.items.length, upperBound(this.offsets, max));
    return Object.freeze({
      start,
      end,
      items: this.items.slice(start, end),
      topSpacer: this.offsets[start] ?? 0,
      bottomSpacer: Math.max(0, this.totalHeight() - (this.offsets[end] ?? this.totalHeight())),
      totalCount: this.totalCount,
      ariaRowCount: this.totalCount,
      renderedCount: end - start,
    });
  }

  focus(key) {
    if (!this.itemByKey.has(key)) return null;
    this.focusedKey = key;
    const { index } = this.itemByKey.get(key);
    const top = this.offsets[index];
    const bottom = this.offsets[index + 1];
    if (top < this.viewport.scrollTop) this.viewport.scrollTop = top;
    else if (bottom > this.viewport.scrollTop + this.viewport.height) this.viewport.scrollTop = Math.max(0, bottom - this.viewport.height);
    this.emit('focus');
    return this.viewport.scrollTop;
  }

  captureAnchor() {
    if (!this.items.length) return null;
    const index = Math.max(0, Math.min(this.items.length - 1, upperBound(this.offsets, this.viewport.scrollTop) - 1));
    return { key: keyOf(this.items[index]), delta: this.viewport.scrollTop - this.offsets[index] };
  }

  restoreAnchor(anchor) {
    if (!anchor) return;
    const entry = this.itemByKey.get(anchor.key);
    if (!entry) return;
    this.viewport.scrollTop = Math.max(0, this.offsets[entry.index] + anchor.delta);
    this.anchor = anchor;
  }

  totalHeight() { return this.offsets[this.offsets.length - 1] ?? 0; }

  rebuildOffsets() {
    const offsets = new Array(this.items.length + 1);
    offsets[0] = 0;
    for (let index = 0; index < this.items.length; index += 1) {
      offsets[index + 1] = offsets[index] + (this.heights.get(keyOf(this.items[index])) ?? this.options.estimatedRowHeight);
    }
    this.offsets = offsets;
  }

  emit(reason) {
    const snapshot = { reason, viewport: { ...this.viewport }, window: this.window(), focusedKey: this.focusedKey };
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
