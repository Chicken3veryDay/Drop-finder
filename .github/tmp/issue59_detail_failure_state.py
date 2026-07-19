from pathlib import Path
import re

path = Path("web/src/features/marketplace/MarketplaceFeature.tsx")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one anchor, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)


replace_once(
'''const EMPTY_DETAIL: MarketplaceProductDetail = {
  productId: "",
  effects: [],
  growEnvironment: "unknown",
};
''',
'''const EMPTY_DETAIL: MarketplaceProductDetail = {
  productId: "",
  effects: [],
  growEnvironment: "unknown",
};

type DetailLoadStatus = "loading" | "ready" | "error";
type DetailLoadEntry = {
  status: DetailLoadStatus;
  message: string | null;
};
''')

replace_once(
'''function ExpandedDetail({
  row,
  detail,
  selectedVariantId,
  onVariantChange,
  onOpenDocument,
}: {
  row: MarketplaceRowProjection;
  detail: MarketplaceProductDetail;
  selectedVariantId: string | undefined;
  onVariantChange(variantId: string): void;
  onOpenDocument(kind: DocumentKind, variant: MarketplaceVariant, element: HTMLElement): void;
}) {
''',
'''function ExpandedDetail({
  row,
  detail,
  detailStatus,
  detailError,
  selectedVariantId,
  onVariantChange,
  onOpenDocument,
  onRetryDetail,
}: {
  row: MarketplaceRowProjection;
  detail: MarketplaceProductDetail;
  detailStatus: DetailLoadStatus;
  detailError: string | null;
  selectedVariantId: string | undefined;
  onVariantChange(variantId: string): void;
  onOpenDocument(kind: DocumentKind, variant: MarketplaceVariant, element: HTMLElement): void;
  onRetryDetail(): void;
}) {
''')

replace_once(
'''  const coa = resolveDocument(variant, "coa");
  const terpene = resolveDocument(variant, "terpene");
''',
'''  const coa = detailStatus === "ready" ? resolveDocument(variant, "coa") : null;
  const terpene = detailStatus === "ready" ? resolveDocument(variant, "terpene") : null;
''')

replace_once(
'''      <div className="df-expanded-facts">
        <p>
          <span>Effects</span>
          <strong>{effects.length > 0 ? effects.join(", ") : "—"}</strong>
        </p>
        <p>
          <span>Grow</span>
          <strong>{detail.growEnvironment === "unknown" ? "Unknown" : detail.growEnvironment}</strong>
        </p>
      </div>
''',
'''      {detailStatus === "error" ? (
        <div className="df-detail-state" role="alert">
          <p>{detailError || "Product details and lab documents could not be loaded."}</p>
          <button
            type="button"
            onClick={(event: any) => {
              stopEvent(event);
              onRetryDetail();
            }}
          >
            Retry details
          </button>
        </div>
      ) : detailStatus === "loading" ? (
        <div className="df-detail-state" role="status" aria-live="polite">
          Loading product details and lab documents…
        </div>
      ) : (
        <div className="df-expanded-facts">
          <p>
            <span>Effects</span>
            <strong>{effects.length > 0 ? effects.join(", ") : "—"}</strong>
          </p>
          <p>
            <span>Grow</span>
            <strong>{detail.growEnvironment === "unknown" ? "Unknown" : detail.growEnvironment}</strong>
          </p>
        </div>
      )}
''')

replace_once(
'''function MarketplaceRow({
  row,
  expanded,
  detail,
  selectedVariantId,
  onToggle,
  onVariantChange,
  onOpenDocument,
}: {
  row: MarketplaceRowProjection;
  expanded: boolean;
  detail: MarketplaceProductDetail;
  selectedVariantId: string | undefined;
  onToggle(): void;
  onVariantChange(variantId: string): void;
  onOpenDocument(kind: DocumentKind, variant: MarketplaceVariant, element: HTMLElement): void;
}) {
''',
'''function MarketplaceRow({
  row,
  expanded,
  detail,
  detailStatus,
  detailError,
  selectedVariantId,
  onToggle,
  onVariantChange,
  onOpenDocument,
  onRetryDetail,
}: {
  row: MarketplaceRowProjection;
  expanded: boolean;
  detail: MarketplaceProductDetail;
  detailStatus: DetailLoadStatus;
  detailError: string | null;
  selectedVariantId: string | undefined;
  onToggle(): void;
  onVariantChange(variantId: string): void;
  onOpenDocument(kind: DocumentKind, variant: MarketplaceVariant, element: HTMLElement): void;
  onRetryDetail(): void;
}) {
''')

replace_once(
'''          row={row}
          detail={detail}
          selectedVariantId={selectedVariantId}
          onVariantChange={onVariantChange}
          onOpenDocument={onOpenDocument}
''',
'''          row={row}
          detail={detail}
          detailStatus={detailStatus}
          detailError={detailError}
          selectedVariantId={selectedVariantId}
          onVariantChange={onVariantChange}
          onOpenDocument={onOpenDocument}
          onRetryDetail={onRetryDetail}
''')

replace_once(
'''  const loadedDetails = useMemo(
    () => loadedDetailState.generationId === catalogGenerationId
      ? loadedDetailState.details
      : {},
    [catalogGenerationId, loadedDetailState],
  );
''',
'''  const loadedDetails = useMemo(
    () => loadedDetailState.generationId === catalogGenerationId
      ? loadedDetailState.details
      : {},
    [catalogGenerationId, loadedDetailState],
  );
  const [detailLoadState, setDetailLoadState] = useState<{
    generationId: string | null;
    entries: Record<string, DetailLoadEntry>;
  }>({ generationId: catalogGenerationId, entries: {} });
  const [detailRetryTokens, setDetailRetryTokens] = useState<Record<string, number>>({});
  const activeDetailLoads = useMemo(
    () => detailLoadState.generationId === catalogGenerationId
      ? detailLoadState.entries
      : {},
    [catalogGenerationId, detailLoadState],
  );
''')

pattern = re.compile(
    r'''  useEffect\(\(\) => \{\n    if \(!expandedProductId \|\| !loadDetail \|\| detailsByProductId\[expandedProductId\] \|\| loadedDetails\[expandedProductId\]\) return;\n    const controller = new AbortController\(\);\n    void loadDetail\(expandedProductId, controller\.signal\)\.then\(\(detail\) => \{.*?\n  \}, \[catalogGenerationId, expandedProductId, loadDetail, detailsByProductId, loadedDetails\]\);''',
    re.S,
)
replacement = '''  useEffect(() => {
    if (!expandedProductId || !loadDetail || detailsByProductId[expandedProductId] || loadedDetails[expandedProductId]) return;
    const productId = expandedProductId;
    const controller = new AbortController();
    setDetailLoadState((current) => ({
      generationId: catalogGenerationId,
      entries: {
        ...(current.generationId === catalogGenerationId ? current.entries : {}),
        [productId]: { status: "loading", message: null },
      },
    }));
    void loadDetail(productId, controller.signal).then((detail) => {
      if (controller.signal.aborted) return;
      setLoadedDetailState((current) => ({
        generationId: catalogGenerationId,
        details: current.generationId === catalogGenerationId
          ? { ...current.details, [detail.productId]: detail }
          : { [detail.productId]: detail },
      }));
      setDetailLoadState((current) => ({
        generationId: catalogGenerationId,
        entries: {
          ...(current.generationId === catalogGenerationId ? current.entries : {}),
          [productId]: { status: "ready", message: null },
        },
      }));
    }).catch((caught: unknown) => {
      if (controller.signal.aborted || (caught instanceof DOMException && caught.name === "AbortError")) return;
      setDetailLoadState((current) => ({
        generationId: catalogGenerationId,
        entries: {
          ...(current.generationId === catalogGenerationId ? current.entries : {}),
          [productId]: {
            status: "error",
            message: "Product details and lab documents could not be loaded.",
          },
        },
      }));
    });
    return () => controller.abort();
  }, [
    catalogGenerationId,
    expandedProductId,
    loadDetail,
    detailsByProductId,
    loadedDetails,
    detailRetryTokens,
  ]);'''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"detail effect replacements: {count}")

replace_once(
'''  const clearFilters = () => setFilters(DEFAULT_FILTERS);

  const openDocument = async (
''',
'''  const clearFilters = () => setFilters(DEFAULT_FILTERS);
  const retryDetail = useCallback((productId: string) => {
    setDetailRetryTokens((current) => ({
      ...current,
      [productId]: (current[productId] ?? 0) + 1,
    }));
  }, []);

  const openDocument = async (
''')

replace_once(
'''      expanded={expandedProductId === row.product.id}
      detail={detailsByProductId[row.product.id] || loadedDetails[row.product.id] || { ...EMPTY_DETAIL, productId: row.product.id }}
      selectedVariantId={selectedVariantIds[row.product.id]}
''',
'''      expanded={expandedProductId === row.product.id}
      detail={detailsByProductId[row.product.id] || loadedDetails[row.product.id] || { ...EMPTY_DETAIL, productId: row.product.id }}
      detailStatus={
        detailsByProductId[row.product.id] || loadedDetails[row.product.id] || !loadDetail
          ? "ready"
          : activeDetailLoads[row.product.id]?.status ?? "loading"
      }
      detailError={activeDetailLoads[row.product.id]?.message ?? null}
      selectedVariantId={selectedVariantIds[row.product.id]}
''')

replace_once(
'''      onOpenDocument={(kind, variant, element) => void openDocument(kind, variant, element, row.product.id)}
    />
''',
'''      onOpenDocument={(kind, variant, element) => void openDocument(kind, variant, element, row.product.id)}
      onRetryDetail={() => retryDetail(row.product.id)}
    />
''')

path.write_text(text, encoding="utf-8")
