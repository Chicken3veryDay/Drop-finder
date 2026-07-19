from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '''const expandedProductIdRef = useRef(expandedProductId);
expandedProductIdRef.current = expandedProductId;
const [asyncWindow, setAsyncWindow] = useState(() => emptyMarketplacePageWindow(queryKey));
''',
    '''const expandedProductIdRef = useRef(expandedProductId);
expandedProductIdRef.current = expandedProductId;
const productsRef = useRef(products);
productsRef.current = products;
const [asyncWindow, setAsyncWindow] = useState(() => emptyMarketplacePageWindow(queryKey));
''',
    "semantic products ref",
)

feature = Path("web/src/features/marketplace/MarketplaceFeature.tsx")
text = feature.read_text(encoding="utf-8")
old_call = "asyncQueryEngine.query(products, filters, sort, {"
new_call = "asyncQueryEngine.query(productsRef.current, filters, sort, {"
if text.count(new_call) != 2:
    count = text.count(old_call)
    if count != 2:
        raise SystemExit(f"async query product snapshot: expected two matches, found {count}")
    text = text.replace(old_call, new_call)
feature.write_text(text, encoding="utf-8")

replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '''}, [asyncQueryEngine, catalogGenerationId, filters, products, queryKey, queryRetryToken, sort]);
''',
    '''}, [asyncQueryEngine, catalogGenerationId, filters, queryKey, queryRetryToken, sort]);
''',
    "page-zero semantic dependency",
)
replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '''}, [activeAsyncWindow, asyncQueryEngine, catalogGenerationId, filters, products, queryKey, queryLoading, sort]);
''',
    '''}, [activeAsyncWindow, asyncQueryEngine, catalogGenerationId, filters, queryKey, queryLoading, sort]);
''',
    "pagination semantic dependency",
)

replace_once(
    "web/src/features/marketplace/MarketplaceFeature.query-path.test.tsx",
    '''  it("retains the synchronous query fallback when no async engine is available", () => {
''',
    '''  it("does not restart page zero when only detail-enrichment fields change", async () => {
    const asynchronousQuery = vi.fn<MarketplaceAsyncQueryCapability["query"]>(async (
      products,
      _filters,
      _sort,
      options,
    ) => ({
      queryKey: options.queryKey,
      offset: options.offset,
      rows: [{
        ...row,
        product: products[0]!,
        activeVariant: products[0]!.variants[0]!,
      }],
      total: 1,
      nextOffset: null,
    }));
    const view = render(
      <MarketplaceFeature
        products={[product]}
        asyncQueryEngine={{ query: asynchronousQuery }}
      />,
    );

    expect(await screen.findByRole("list", { name: "1 marketplace results" })).toBeInTheDocument();
    expect(asynchronousQuery).toHaveBeenCalledTimes(1);

    const enrichedProduct: MarketplaceProduct = {
      ...product,
      vendorFaviconUrl: "https://example.test/favicon.png",
      variants: [{
        ...product.variants[0]!,
        imageUrl: "https://example.test/blue-example.jpg",
      }],
    };
    view.rerender(
      <MarketplaceFeature
        products={[enrichedProduct]}
        asyncQueryEngine={{ query: asynchronousQuery }}
      />,
    );

    await waitFor(() => expect(asynchronousQuery).toHaveBeenCalledTimes(1));
  });

  it("retains the synchronous query fallback when no async engine is available", () => {
''',
    "detail enrichment query regression",
)

replace_once(
    "web/tests/e2e/fixtures/harness.js",
    '''  if (nextOffset != null && viewport.scrollTop + viewport.clientHeight > virtual.totalHeight() - 900) {
''',
    '''  if (nextOffset != null && viewport.scrollTop + viewport.clientHeight > virtual.loadedRange().endPx - 900) {
''',
    "harness retained edge pagination",
)

replace_once(
    "web/tests/e2e/platform.spec.mjs",
    '''  for (let index = 0; index < 24; index += 1) {
    await page.locator('#viewport').evaluate(element => { element.scrollTop = element.scrollHeight; element.dispatchEvent(new Event('scroll')); });
    await page.waitForTimeout(25);
  }
''',
    '''  for (let index = 0; index < 24; index += 1) {
    const beforeEnd = await page.evaluate(() => window.__platformHarness.virtual.loadedRange().endOffset);
    await page.locator('#viewport').evaluate(element => {
      const range = window.__platformHarness.virtual.loadedRange();
      element.scrollTop = Math.max(0, range.endPx - element.clientHeight + 1);
      element.dispatchEvent(new Event('scroll'));
    });
    await expect.poll(
      () => page.evaluate(() => window.__platformHarness.virtual.loadedRange().endOffset),
    ).toBeGreaterThan(beforeEnd);
  }
''',
    "incremental retained-edge browser scroll",
)
