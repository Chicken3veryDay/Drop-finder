import {
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
  type ReactNode,
} from "react";
import {
  MarketplaceFeature as FlowerMarketplaceFeature,
} from "./MarketplaceFeature";
import type { MarketplaceFeatureProps } from "./marketplace-core";
import "./type-aware-marketplace.css";

export type ProductType =
  | "cannabis_flower"
  | "cannabis_vape"
  | "psilocybin_mushroom"
  | "psilocybin_vape";

type CatalogEnvelope = {
  products?: unknown[];
  products_by_type?: Record<string, unknown>;
};

export type RawCatalogProduct = Record<string, unknown>;

type SortKey =
  | "price_asc"
  | "price_desc"
  | "metric_asc"
  | "metric_desc"
  | "completeness_desc"
  | "name_asc";

const PRODUCT_TYPES: readonly ProductType[] = [
  "cannabis_flower",
  "cannabis_vape",
  "psilocybin_mushroom",
  "psilocybin_vape",
];

const CONTROLLED_TYPES = new Set<ProductType>([
  "psilocybin_mushroom",
  "psilocybin_vape",
]);

const TYPE_LABELS: Record<ProductType, string> = {
  cannabis_flower: "Flower",
  cannabis_vape: "Cannabis vapes",
  psilocybin_mushroom: "Mushrooms",
  psilocybin_vape: "Psilocybin vapes",
};

const TYPE_DESCRIPTIONS: Record<ProductType, string> = {
  cannabis_flower: "Strict THCA flower marketplace",
  cannabis_vape: "Cannabis vape products with milliliter pricing",
  psilocybin_mushroom: "Informational psilocybin mushroom metadata",
  psilocybin_vape: "Informational psilocybin vape metadata",
};

const objectValue = (value: unknown): Record<string, unknown> | null =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;

const stringValue = (value: unknown): string =>
  typeof value === "string" ? value.trim() : "";

const numberValue = (value: unknown): number | null => {
  if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) {
    return null;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const evidenceValue = (product: RawCatalogProduct): Record<string, unknown> =>
  objectValue(product.classification_evidence) ?? {};

export const inferProductType = (product: RawCatalogProduct): ProductType | null => {
  const evidence = evidenceValue(product);
  const explicit = stringValue(product.primary_type ?? evidence.primary_type);
  if (PRODUCT_TYPES.includes(explicit as ProductType)) return explicit as ProductType;
  if (evidence.explicit_thca === true && evidence.explicit_flower === true) {
    return "cannabis_flower";
  }
  return null;
};

export const normalizeRawCatalog = (payload: unknown): RawCatalogProduct[] => {
  const envelope = objectValue(payload) as CatalogEnvelope | null;
  const products = Array.isArray(envelope?.products) ? envelope.products : [];
  return products.flatMap((value): RawCatalogProduct[] => {
    const product = objectValue(value);
    return product && inferProductType(product) ? [product] : [];
  });
};

const productId = (product: RawCatalogProduct): string =>
  stringValue(product.id ?? product.product_id)
  || `${stringValue(product.source_id)}:${stringValue(product.name)}:${stringValue(product.variant)}`;

const productName = (product: RawCatalogProduct): string =>
  stringValue(product.strain ?? product.strain_name ?? product.name) || "Unnamed product";

const vendorName = (product: RawCatalogProduct): string =>
  stringValue(product.vendor ?? product.vendor_name) || "Unknown vendor";

const money = (value: unknown): string => {
  const parsed = numberValue(value);
  return parsed === null
    ? "—"
    : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(parsed);
};

const decimal = (value: unknown, suffix = ""): string => {
  const parsed = numberValue(value);
  return parsed === null
    ? "—"
    : `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(parsed)}${suffix}`;
};

const listValue = (value: unknown): string => {
  if (!Array.isArray(value)) return "—";
  const entries = value.map(stringValue).filter(Boolean);
  return entries.length ? entries.join(", ") : "—";
};

const comparisonValue = (product: RawCatalogProduct, type: ProductType): number | null =>
  type === "cannabis_vape" || type === "psilocybin_vape"
    ? numberValue(product.price_per_ml ?? product.comparison_price)
    : numberValue(product.price_per_gram ?? product.comparison_price);

const quantityValue = (product: RawCatalogProduct, type: ProductType): string =>
  type === "cannabis_vape" || type === "psilocybin_vape"
    ? decimal(product.volume_ml, " mL")
    : decimal(product.grams, " g");

const comparisonLabel = (type: ProductType): string =>
  type === "cannabis_vape" || type === "psilocybin_vape" ? "$/mL" : "$/g";

const potencyValue = (product: RawCatalogProduct, type: ProductType): string => {
  if (type === "psilocybin_vape") return decimal(product.psilocybin_percent, "%");
  if (type === "psilocybin_mushroom") return decimal(
    product.claimed_potency_percent ?? product.psilocybin_percent,
    "%",
  );
  return decimal(product.thca, "%");
};

const terpeneValue = (product: RawCatalogProduct): string => {
  const total = numberValue(product.total_terpenes_percent);
  const names = listValue(product.terpenes);
  if (total !== null && names !== "—") return `${decimal(total, "%")} · ${names}`;
  if (total !== null) return decimal(total, "%");
  return names;
};

const publicPurchaseUrl = (product: RawCatalogProduct, type: ProductType): string => {
  if (CONTROLLED_TYPES.has(type)) return "";
  const target = stringValue(product.public_purchase_url ?? product.url);
  try {
    const parsed = new URL(target);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.toString() : "";
  } catch {
    return "";
  }
};

const documentUrl = (product: RawCatalogProduct, targetKind: "coa" | "terpene"): string => {
  const documents = Array.isArray(product.documents) ? product.documents : [];
  for (const value of documents) {
    const document = objectValue(value);
    if (!document) continue;
    const kind = stringValue(document.kind);
    if (kind !== targetKind && kind !== "combined") continue;
    const target = stringValue(document.public_url ?? document.url);
    try {
      const parsed = new URL(target);
      if (["http:", "https:"].includes(parsed.protocol)) return parsed.toString();
    } catch {
      continue;
    }
  }
  return "";
};

const completenessValue = (product: RawCatalogProduct): string => {
  const score = numberValue(product.completeness_score);
  return score === null ? "—" : `${Math.max(0, Math.min(100, Math.round(score)))}%`;
};

function ProductTypeTabs({
  activeType,
  counts,
  onSelect,
}: {
  activeType: ProductType;
  counts: Record<ProductType, number>;
  onSelect(type: ProductType): void;
}) {
  return (
    <nav className="df-type-nav" aria-label="Product type">
      <div className="df-type-tabs" role="tablist" aria-label="Marketplace product type">
        {PRODUCT_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            role="tab"
            aria-selected={activeType === type}
            aria-controls={`df-type-panel-${type}`}
            id={`df-type-tab-${type}`}
            className="df-type-tab"
            onClick={() => onSelect(type)}
          >
            <span>{TYPE_LABELS[type]}</span>
            <span className="df-type-count" aria-label={`${counts[type]} products`}>
              {counts[type]}
            </span>
          </button>
        ))}
      </div>
      <p>{TYPE_DESCRIPTIONS[activeType]}</p>
    </nav>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="df-type-field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function TypedProductCard({
  product,
  type,
}: {
  product: RawCatalogProduct;
  type: Exclude<ProductType, "cannabis_flower">;
}) {
  const [expanded, setExpanded] = useState(false);
  const purchaseUrl = publicPurchaseUrl(product, type);
  const coaUrl = documentUrl(product, "coa");
  const controlled = CONTROLLED_TYPES.has(type);
  const metric = comparisonValue(product, type);

  return (
    <article className="df-type-card" data-product-type={type}>
      <header>
        <div>
          <p className="df-type-vendor">{vendorName(product)}</p>
          <h3>{productName(product)}</h3>
        </div>
        <span className="df-completeness" title="Source field completeness">
          {completenessValue(product)}
        </span>
      </header>

      <dl className="df-type-grid">
        {type === "psilocybin_mushroom" ? (
          <>
            <Field label="Species">{stringValue(product.species) || "—"}</Field>
            <Field label="Weight">{quantityValue(product, type)}</Field>
            <Field label="Potency">{potencyValue(product, type)}</Field>
          </>
        ) : (
          <>
            <Field label="Device">{stringValue(product.device_type) || "—"}</Field>
            <Field label="Volume">{quantityValue(product, type)}</Field>
            <Field label={type === "psilocybin_vape" ? "Psilocybin" : "Terpenes"}>
              {type === "psilocybin_vape" ? potencyValue(product, type) : terpeneValue(product)}
            </Field>
          </>
        )}
        <Field label="Price">{money(product.price)}</Field>
        <Field label={comparisonLabel(type)}>{metric === null ? "—" : money(metric)}</Field>
        <Field label="COA">
          {coaUrl ? <a href={coaUrl} target="_blank" rel="noreferrer">Open</a> : "—"}
        </Field>
      </dl>

      <footer>
        <button
          type="button"
          className="df-type-details-button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Hide details" : "More details"}
        </button>
        {purchaseUrl ? (
          <a className="df-type-shop-link" href={purchaseUrl} target="_blank" rel="noreferrer">
            View product
          </a>
        ) : (
          <span className="df-type-information-only">
            {controlled ? "Informational listing" : "Product link unavailable"}
          </span>
        )}
      </footer>

      {expanded ? (
        <div className="df-type-expanded">
          <dl>
            <Field label="Type tags">{listValue(product.type_tags)}</Field>
            <Field label="Puff count">{decimal(product.puff_count)}</Field>
            <Field label="Availability">{stringValue(product.availability) || "—"}</Field>
            <Field label="Collected">{stringValue(product.collected_at) || "—"}</Field>
            <Field label="Source variant">{stringValue(product.variant) || "—"}</Field>
          </dl>
          {controlled ? (
            <p>
              Public metadata only. Purchase links are not published for controlled psilocybin records.
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function TypedCatalogSection({
  type,
  products,
  loading,
  error,
  onRetry,
}: {
  type: Exclude<ProductType, "cannabis_flower">;
  products: readonly RawCatalogProduct[];
  loading: boolean;
  error: string | null;
  onRetry(): void;
}) {
  const [search, setSearch] = useState("");
  const [vendor, setVendor] = useState("");
  const [sort, setSort] = useState<SortKey>("price_asc");

  const vendors = useMemo(
    () => [...new Set(products.map(vendorName))].sort((left, right) => left.localeCompare(right)),
    [products],
  );

  const visible = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    const rows = products.filter((product) => {
      if (vendor && vendorName(product) !== vendor) return false;
      if (!query) return true;
      return `${vendorName(product)}\n${productName(product)}\n${stringValue(product.species)}`
        .toLocaleLowerCase()
        .includes(query);
    });
    const compareNullable = (left: number | null, right: number | null, direction = 1): number => {
      if (left === null) return right === null ? 0 : 1;
      if (right === null) return -1;
      return direction * (left - right);
    };
    return rows.sort((left, right) => {
      if (sort === "price_asc") return compareNullable(numberValue(left.price), numberValue(right.price));
      if (sort === "price_desc") return compareNullable(numberValue(left.price), numberValue(right.price), -1);
      if (sort === "metric_asc") return compareNullable(comparisonValue(left, type), comparisonValue(right, type));
      if (sort === "metric_desc") return compareNullable(comparisonValue(left, type), comparisonValue(right, type), -1);
      if (sort === "completeness_desc") {
        return compareNullable(
          numberValue(left.completeness_score),
          numberValue(right.completeness_score),
          -1,
        );
      }
      return productName(left).localeCompare(productName(right));
    });
  }, [products, search, sort, type, vendor]);

  const onSort = (event: ChangeEvent<HTMLSelectElement>) => {
    setSort(event.target.value as SortKey);
  };

  if (loading) {
    return <div className="df-type-state" role="status">Loading {TYPE_LABELS[type].toLowerCase()}…</div>;
  }
  if (error) {
    return (
      <div className="df-type-state" role="alert">
        <p>{error}</p>
        <button type="button" onClick={onRetry}>Retry</button>
      </div>
    );
  }

  return (
    <section
      className="df-type-panel"
      id={`df-type-panel-${type}`}
      role="tabpanel"
      aria-labelledby={`df-type-tab-${type}`}
    >
      <div className="df-type-controls" aria-label={`${TYPE_LABELS[type]} filters`}>
        <label>
          <span>Search</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Vendor or product"
          />
        </label>
        <label>
          <span>Vendor</span>
          <select value={vendor} onChange={(event) => setVendor(event.target.value)}>
            <option value="">All vendors</option>
            {vendors.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>
          <span>Sort</span>
          <select value={sort} onChange={onSort}>
            <option value="price_asc">Lowest price</option>
            <option value="price_desc">Highest price</option>
            <option value="metric_asc">Lowest {comparisonLabel(type)}</option>
            <option value="metric_desc">Highest {comparisonLabel(type)}</option>
            <option value="completeness_desc">Most complete</option>
            <option value="name_asc">Product A–Z</option>
          </select>
        </label>
      </div>

      <p className="df-type-summary" role="status">
        Showing {visible.length} of {products.length} {TYPE_LABELS[type].toLowerCase()}
      </p>

      {visible.length ? (
        <div className="df-type-results" role="list">
          {visible.map((product) => (
            <div role="listitem" key={productId(product)}>
              <TypedProductCard product={product} type={type} />
            </div>
          ))}
        </div>
      ) : (
        <div className="df-type-state">
          <p>No products match this product type and filter set.</p>
          <button type="button" onClick={() => {
            setSearch("");
            setVendor("");
          }}>
            Clear filters
          </button>
        </div>
      )}
    </section>
  );
}

export function TypeAwareMarketplaceFeature(props: MarketplaceFeatureProps & { catalogGenerationId?: string | null }) {
  const [activeType, setActiveType] = useState<ProductType>("cannabis_flower");
  const [rawProducts, setRawProducts] = useState<RawCatalogProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [rawError, setRawError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    setLoading(true);
    setRawError(null);
    const catalogUrl = new URL("./data/catalog.json", document.baseURI).toString();
    void fetch(catalogUrl, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Catalog request failed with HTTP ${response.status}`);
        return response.json() as Promise<unknown>;
      })
      .then((payload) => {
        if (!current) return;
        setRawProducts(normalizeRawCatalog(payload));
      })
      .catch((error: unknown) => {
        if (!current || controller.signal.aborted) return;
        setRawError(error instanceof Error ? error.message : "The multi-product catalog could not be loaded.");
      })
      .finally(() => {
        if (current && !controller.signal.aborted) setLoading(false);
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [reloadToken]);

  const productsByType = useMemo(() => {
    const grouped: Record<ProductType, RawCatalogProduct[]> = {
      cannabis_flower: [],
      cannabis_vape: [],
      psilocybin_mushroom: [],
      psilocybin_vape: [],
    };
    for (const product of rawProducts) {
      const type = inferProductType(product);
      if (type) grouped[type].push(product);
    }
    return grouped;
  }, [rawProducts]);

  const counts = useMemo<Record<ProductType, number>>(
    () => ({
      cannabis_flower: props.products.length || productsByType.cannabis_flower.length,
      cannabis_vape: productsByType.cannabis_vape.length,
      psilocybin_mushroom: productsByType.psilocybin_mushroom.length,
      psilocybin_vape: productsByType.psilocybin_vape.length,
    }),
    [productsByType, props.products.length],
  );

  return (
    <section className="df-type-aware-marketplace" aria-label="Type-aware marketplace">
      <ProductTypeTabs activeType={activeType} counts={counts} onSelect={setActiveType} />
      {activeType === "cannabis_flower" ? (
        <div
          id="df-type-panel-cannabis_flower"
          role="tabpanel"
          aria-labelledby="df-type-tab-cannabis_flower"
        >
          <FlowerMarketplaceFeature {...props} />
        </div>
      ) : (
        <TypedCatalogSection
          type={activeType}
          products={productsByType[activeType]}
          loading={loading}
          error={rawError}
          onRetry={() => setReloadToken((value) => value + 1)}
        />
      )}
    </section>
  );
}
