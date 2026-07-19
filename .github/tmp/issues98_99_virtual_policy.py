from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


adapter = Path("web/src/platform/virtualization/virtual-marketplace-adapter.js")
replace_once(
    adapter,
    '''    if (priorAnchor && this.itemByKey.has(priorAnchor.key)) this.restoreAnchor(priorAnchor);
    else if (this.baseOffset === 0) this.viewport.scrollTop = 0;
    if (this.focusedKey && !this.itemByKey.has(this.focusedKey)) this.focusedKey = null;
    this.emit('replace-pages');
  }
''',
    '''    if (priorAnchor && this.itemByKey.has(priorAnchor.key)) this.restoreAnchor(priorAnchor);
    else if (this.baseOffset === 0) this.viewport.scrollTop = 0;
    if (this.focusedKey && !this.itemByKey.has(this.focusedKey)) this.focusedKey = null;
    else if (this.focusedKey) this.ensureVisible(this.focusedKey);
    this.emit('replace-pages');
    return this.viewport.scrollTop;
  }
''',
)
replace_once(
    adapter,
    '''  setViewport(scrollTop, height) {
    this.viewport = { scrollTop: Math.max(0, scrollTop), height: Math.max(0, height) };
    this.anchor = this.captureAnchor();
    this.emit('viewport');
  }
''',
    '''  setViewport(scrollTop, height) {
    this.viewport = { scrollTop: Math.max(0, scrollTop), height: Math.max(0, height) };
    if (this.focusedKey) this.ensureVisible(this.focusedKey);
    this.anchor = this.captureAnchor();
    this.emit('viewport');
    return this.viewport.scrollTop;
  }
''',
)
replace_once(
    adapter,
    '''  focus(key) {
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
''',
    '''  focus(key) {
    const entry = this.itemByKey.get(key);
    if (!entry) return null;
    this.focusedKey = key;
    this.ensureVisible(key);
    this.emit('focus');
    return this.viewport.scrollTop;
  }

  blur(key = this.focusedKey) {
    if (!this.focusedKey || key !== this.focusedKey) return false;
    this.focusedKey = null;
    this.emit('blur');
    return true;
  }

  ensureVisible(key) {
    const entry = this.itemByKey.get(key);
    if (!entry) return this.viewport.scrollTop;
    const loaded = this.loadedRange();
    const top = loaded.startPx + this.offsets[entry.index];
    const bottom = loaded.startPx + this.offsets[entry.index + 1];
    if (top < this.viewport.scrollTop) this.viewport.scrollTop = top;
    else if (bottom > this.viewport.scrollTop + this.viewport.height) {
      this.viewport.scrollTop = Math.max(0, bottom - this.viewport.height);
    }
    return this.viewport.scrollTop;
  }
''',
)

integration = Path("web/src/features/integration/register-marketplace-props.tsx")
replace_once(
    integration,
    '''  }): void;
  setViewport(scrollTop: number, height: number): void;
  measure(key: string, height: number): boolean;
''',
    '''  }): number;
  setViewport(scrollTop: number, height: number): number;
  focus(key: string): number | null;
  blur(key?: string | null): boolean;
  measure(key: string, height: number): boolean;
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
  model,
  onFocus,
  onBlur,
  children,
}: {
  productId: string;
  model: VirtualModel;
  onFocus(productId: string): void;
  onBlur(productId: string): void;
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
      onFocusCapture={() => onFocus(productId)}
      onBlurCapture={(event) => {
        const next = event.relatedTarget;
        if (!(next instanceof Node) || !event.currentTarget.contains(next)) onBlur(productId);
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
  const previousQueryKeyRef = useRef<string | null>(null);
  const focusedProductRef = useRef<string | null>(null);
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
    const previousQueryKey = previousQueryKeyRef.current;
    const semanticQueryChanged = previousQueryKey !== null && previousQueryKey !== queryKey;
    const nextScrollTop = model.replacePages({
      pages: virtualPages,
      total,
      version: virtualPages.length,
      queryKey,
      preserveAnchor: previousQueryKey === queryKey,
    });
    previousQueryKeyRef.current = queryKey;

    const viewport = viewportRef.current;
    if (viewport && Math.abs(viewport.scrollTop - nextScrollTop) > 0.5) {
      viewport.scrollTop = nextScrollTop;
    }

    const focusedProduct = focusedProductRef.current;
    if (focusedProduct && !virtualPages.some((page) => page.rows.some((row) => row.productId === focusedProduct))) {
      focusedProductRef.current = null;
      model.blur(focusedProduct);
      viewport?.focus({ preventScroll: true });
    } else if (semanticQueryChanged && viewport && nextScrollTop === 0) {
      viewport.scrollTop = 0;
    }
  }, [model, queryKey, total, virtualPages]);
''',
)
replace_once(
    integration,
    '''    const update = () => model.setViewport(viewport.scrollTop, viewport.clientHeight);
    update();
''',
    '''    const update = () => {
      const controlledScrollTop = model.setViewport(viewport.scrollTop, viewport.clientHeight);
      if (Math.abs(viewport.scrollTop - controlledScrollTop) > 0.5) viewport.scrollTop = controlledScrollTop;
    };
    update();
''',
)
replace_once(
    integration,
    '''  const windowState = model.window();
  const onScroll = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    model.setViewport(viewport.scrollTop, viewport.clientHeight);
''',
    '''  const windowState = model.window();
  const focusRow = useCallback((productId: string) => {
    focusedProductRef.current = productId;
    const controlledScrollTop = model.focus(productId);
    const viewport = viewportRef.current;
    if (viewport && controlledScrollTop !== null && Math.abs(viewport.scrollTop - controlledScrollTop) > 0.5) {
      viewport.scrollTop = controlledScrollTop;
    }
  }, [model]);
  const blurRow = useCallback((productId: string) => {
    if (focusedProductRef.current === productId) focusedProductRef.current = null;
    model.blur(productId);
  }, [model]);
  const onScroll = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const controlledScrollTop = model.setViewport(viewport.scrollTop, viewport.clientHeight);
    if (Math.abs(viewport.scrollTop - controlledScrollTop) > 0.5) viewport.scrollTop = controlledScrollTop;
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
      role="list"
      aria-label="Marketplace results"
      tabIndex={-1}
      onScroll={onScroll}
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
          model={model}
          onFocus={focusRow}
          onBlur={blurRow}
        >
          {renderRow(item.row)}
        </MeasuredRow>
''',
)
