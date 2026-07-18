import { CatalogGenerationClient } from '../../platform/catalog/catalog-generation-client.js';

let renderabilityContractPromise = null;
let getCanonicalVariants = null;

async function loadRenderabilityContract() {
  if (!renderabilityContractPromise) {
    renderabilityContractPromise = import('../marketplace/marketplace-core.ts').then(module => {
      if (typeof module.getInStockVariants !== 'function') {
        throw new TypeError('Marketplace renderability contract is unavailable');
      }
      getCanonicalVariants = module.getInStockVariants;
      return getCanonicalVariants;
    });
  }
  return renderabilityContractPromise;
}

const objectValue = value => (
  typeof value === 'object' && value !== null && !Array.isArray(value) ? value : null
);

const stringValue = value => typeof value === 'string' ? value.trim() : '';

const numberValue = value => {
  if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

function mapVariant(raw) {
  const row = objectValue(raw);
  if (!row) return null;
  const id = stringValue(row.variant_id ?? row.id);
  const grams = numberValue(row.grams ?? row.weight);
  const currentPrice = numberValue(row.current_price ?? row.price);
  const pricePerGram = numberValue(row.price_per_gram);
  const productUrl = stringValue(row.product_url ?? row.variant_url);
  if (!id || !grams || !currentPrice || !pricePerGram || !productUrl) return null;
  return {
    id,
    grams,
    sourceWeightLabel: stringValue(row.source_weight_label) || `${grams} g`,
    currentPrice,
    originalPrice: numberValue(row.original_price),
    pricePerGram,
    inStock: row.in_stock === true,
    productUrl,
    imageUrl: stringValue(row.image_url) || null,
    coa: null,
    terpeneDocument: null,
  };
}

function canonicalizeProduct(rawProduct, getInStockVariants) {
  const product = objectValue(rawProduct);
  if (!product) return null;
  const productId = stringValue(product.product_id ?? product.id);
  const vendorId = stringValue(product.vendor_id);
  const vendorName = stringValue(product.vendor_name ?? product.vendor);
  const strainName = stringValue(product.strain_name ?? product.strain);
  if (!productId || !vendorId || !vendorName || !strainName) return null;
  const rawVariants = Array.isArray(product.variants) ? product.variants : [];
  const pairs = rawVariants.flatMap(raw => {
    const mapped = mapVariant(raw);
    return mapped ? [{ raw, mapped }] : [];
  });
  const canonical = getInStockVariants({
    id: productId,
    vendorId,
    vendorName,
    strainName,
    lineage: 'unknown',
    totalThcDisplay: null,
    rating: null,
    reviewCount: null,
    variants: pairs.map(pair => pair.mapped),
  });
  if (canonical.length === 0) return null;
  const sourceByVariant = new Map(pairs.map(pair => [pair.mapped, pair.raw]));
  return {
    ...product,
    variants: canonical.map(variant => sourceByVariant.get(variant)).filter(Boolean),
  };
}

function canonicalizeCatalogIndexSync(index) {
  if (!getCanonicalVariants) {
    throw new Error('Marketplace renderability contract has not been initialized');
  }
  const envelope = objectValue(index);
  if (!envelope || !Array.isArray(envelope.products)) return index;
  return {
    ...envelope,
    products: envelope.products
      .map(product => canonicalizeProduct(product, getCanonicalVariants))
      .filter(Boolean),
  };
}

function canonicalizeCatalogGenerationSync(generation) {
  const envelope = objectValue(generation);
  if (!envelope) return generation;
  const index = canonicalizeCatalogIndexSync(envelope.index);
  if (index === envelope.index) return generation;
  return Object.freeze({ ...envelope, index });
}

export async function canonicalizeCatalogIndex(index) {
  await loadRenderabilityContract();
  return canonicalizeCatalogIndexSync(index);
}

export async function canonicalizeCatalogGeneration(generation) {
  await loadRenderabilityContract();
  return canonicalizeCatalogGenerationSync(generation);
}

export class CanonicalCatalogGenerationClient extends CatalogGenerationClient {
  async loadCompleteGeneration(signal) {
    await loadRenderabilityContract();
    return canonicalizeCatalogGenerationSync(await super.loadCompleteGeneration(signal));
  }

  async initialize(options) {
    await loadRenderabilityContract();
    return canonicalizeCatalogGenerationSync(await super.initialize(options));
  }

  async refresh(options) {
    await loadRenderabilityContract();
    return canonicalizeCatalogGenerationSync(await super.refresh(options));
  }

  activate(generation, source) {
    super.activate(canonicalizeCatalogGenerationSync(generation), source);
  }
}
