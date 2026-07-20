from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


integration = "web/src/features/integration/register-marketplace-props.tsx"
replace_once(
    integration,
    '''type VirtualWindow = {
  items: Array<{ productId: string; row: MarketplaceRowProjection }>;
  topSpacer: number;
  bottomSpacer: number;
  totalCount: number;
};
''',
    '''type VirtualWindow = {
  items: Array<{ productId: string; row: MarketplaceRowProjection; logicalIndex: number }>;
  topSpacer: number;
  bottomSpacer: number;
  totalCount: number;
};
''',
)
replace_once(
    integration,
    '''  measure(key: string, height: number): boolean;
  window(): VirtualWindow;
  loadedRange(): { startPx: number; endPx: number };
''',
    '''  measure(key: string, height: number): boolean;
  focus(key: string): number | null;
  blur(key?: string | null): void;
  window(): VirtualWindow;
  loadedRange(): { startPx: number; endPx: number };
''',
)
replace_once(
    integration,
    '''function MeasuredRow({
  productId,
  model,
  children,
}: {
  productId: string;
  model: VirtualModel;
  children: ReactNode;
}) {
''',
    '''function MeasuredRow({
  productId,
  logicalIndex,
  totalCount,
  model,
  onFocused,
  children,
}: {
  productId: string;
  logicalIndex: number;
  totalCount: number;
  model: VirtualModel;
  onFocused(productId: string): void;
  children: ReactNode;
}) {
''',
)
replace_once(
    integration,
    '''  return <div ref={ref} data-virtual-product={productId} role="listitem">{children}</div>;
}

function VirtualizedMarketplace({
''',
    '''  return (
    <div
      ref={ref}
      data-virtual-product={productId}
      role="listitem"
      aria-posinset={logicalIndex}
      aria-setsize={totalCount}
      onFocusCapture={() => onFocused(productId)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) model.blur(productId);
      }}
    >
      {children}
    </div>
  );
}

export function VirtualizedMarketplace({
''',
)
replace_once(
    integration,
    '''  const viewportRef = useRef<HTMLDivElement>(null);
  const [, setRevision] = useState(0);
''',
    '''  const viewportRef = useRef<HTMLDivElement>(null);
  const previousQueryKey = useRef<string | null>(null);
  const [, setRevision] = useState(0);
''',
)
replace_once(
    integration,
    '''  useLayoutEffect(() => {
    model.replacePages({
      pages: virtualPages,
      total,
      version: virtualPages.length,
      queryKey,
      preserveAnchor: true,
    });
  }, [model, queryKey, total, virtualPages]);
''',
    '''  useLayoutEffect(() => {
    const preserveAnchor = previousQueryKey.current === queryKey;
    previousQueryKey.current = queryKey;
    model.replacePages({
      pages: virtualPages,
      total,
      version: virtualPages.length,
      queryKey,
      preserveAnchor,
    });
    const viewport = viewportRef.current;
    if (!preserveAnchor && viewport) {
      viewport.scrollTop = 0;
      model.setViewport(0, viewport.clientHeight);
    }
  }, [model, queryKey, total, virtualPages]);
''',
)
replace_once(
    integration,
    '''  const windowState = model.window();
  const onScroll = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    model.setViewport(viewport.scrollTop, viewport.clientHeight);
    const range = model.loadedRange();
''',
    '''  const windowState = model.window();
  const onRowFocused = useCallback((productId: string) => {
    const viewport = viewportRef.current;
    const nextScrollTop = model.focus(productId);
    if (viewport && nextScrollTop !== null && Math.abs(viewport.scrollTop - nextScrollTop) >= 0.5) {
      viewport.scrollTop = nextScrollTop;
      model.setViewport(nextScrollTop, viewport.clientHeight);
    }
  }, [model]);
  const onScroll = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const activeRow = document.activeElement instanceof Element
      ? document.activeElement.closest<HTMLElement>("[data-virtual-product]")
      : null;
    const activeProductId = activeRow?.dataset.virtualProduct ?? null;
    model.setViewport(viewport.scrollTop, viewport.clientHeight);
    if (activeProductId && !model.window().items.some((item) => item.productId === activeProductId)) {
      model.blur(activeProductId);
      viewport.focus({ preventScroll: true });
    }
    const range = model.loadedRange();
''',
)
replace_once(
    integration,
    '''      ref={viewportRef}
      className="df-virtual-viewport"
      onScroll={onScroll}
    >
''',
    '''      ref={viewportRef}
      className="df-virtual-viewport"
      onScroll={onScroll}
      tabIndex={-1}
      aria-label="Marketplace results viewport"
    >
''',
)
replace_once(
    integration,
    '''        <MeasuredRow key={item.productId} productId={item.productId} model={model}>
          {renderRow(item.row)}
        </MeasuredRow>
''',
    '''        <MeasuredRow
          key={item.productId}
          productId={item.productId}
          logicalIndex={item.logicalIndex}
          totalCount={windowState.totalCount}
          model={model}
          onFocused={onRowFocused}
        >
          {renderRow(item.row)}
        </MeasuredRow>
''',
)

adapter = "web/src/platform/virtualization/virtual-marketplace-adapter.js"
replace_once(
    adapter,
    '''      items: this.items.slice(start, end),
      topSpacer: loaded.startPx + (this.offsets[start] ?? 0),
''',
    '''      items: this.items.slice(start, end).map(item => ({
        ...item,
        logicalIndex: (this.itemByKey.get(keyOf(item))?.globalIndex ?? 0) + 1,
      })),
      topSpacer: loaded.startPx + (this.offsets[start] ?? 0),
''',
)
replace_once(
    adapter,
    '''  focus(key) {
    const entry = this.itemByKey.get(key);
    if (!entry) return null;
    this.focusedKey = key;
''',
    '''  focus(key) {
    const entry = this.itemByKey.get(key);
    if (!entry) return null;
    this.focusedKey = key;
''',
)
replace_once(
    adapter,
    '''    this.emit('focus');
    return this.viewport.scrollTop;
  }

  captureAnchor() {
''',
    '''    this.emit('focus');
    return this.viewport.scrollTop;
  }

  blur(key = null) {
    if (key != null && this.focusedKey !== String(key)) return;
    if (this.focusedKey == null) return;
    this.focusedKey = null;
    this.emit('blur');
  }

  captureAnchor() {
''',
)
