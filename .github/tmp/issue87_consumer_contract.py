from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


verify = "scripts/catalog_v4/verify.py"
replace_once(
    verify,
    "from typing import Any\n",
    "from typing import Any\nfrom urllib.parse import urlsplit\n",
)
replace_once(
    verify,
    "def _variant_identity(variant: dict[str, Any], *, product_id: str, detail: bool) -> tuple[float, str]:\n",
    "def _required_text(value: Any, *, field: str, product_id: str) -> str:\n"
    "    normalized = str(value or \"\").strip()\n"
    "    if not normalized:\n"
    "        raise VerificationError(f\"missing {field}: {product_id}\")\n"
    "    return normalized\n\n\n"
    "def _https_url(value: Any, *, product_id: str, variant_id: str) -> str:\n"
    "    normalized = str(value or \"\").strip()\n"
    "    try:\n"
    "        parsed = urlsplit(normalized)\n"
    "    except ValueError as exc:\n"
    "        raise VerificationError(f\"invalid variant URL: {product_id} {variant_id}\") from exc\n"
    "    if parsed.scheme != \"https\" or not parsed.netloc:\n"
    "        raise VerificationError(f\"invalid variant URL: {product_id} {variant_id}\")\n"
    "    return normalized\n\n\n"
    "def _variant_identity(variant: dict[str, Any], *, product_id: str, detail: bool) -> tuple[float, str]:\n",
)
replace_once(
    verify,
    "    url_field = \"variant_url\" if detail else \"product_url\"\n"
    "    variant_url = str(variant.get(url_field) or \"\")\n"
    "    if not variant_url:\n"
    "        raise VerificationError(f\"missing variant URL: {product_id} {variant_id}\")\n"
    "    return grams, variant_url\n",
    "    url_field = \"variant_url\" if detail else \"product_url\"\n"
    "    variant_url = _https_url(variant.get(url_field), product_id=product_id, variant_id=variant_id)\n"
    "    return grams, variant_url\n",
)
replace_once(
    verify,
    "        product_ids.add(product_id)\n"
    "        if product.get(\"lineage\") not in allowed_lineages:\n",
    "        product_ids.add(product_id)\n"
    "        _required_text(product.get(\"vendor_id\"), field=\"vendor id\", product_id=product_id)\n"
    "        _required_text(product.get(\"vendor_name\"), field=\"vendor name\", product_id=product_id)\n"
    "        _required_text(product.get(\"strain_name\"), field=\"strain name\", product_id=product_id)\n"
    "        if product.get(\"lineage\") not in allowed_lineages:\n",
)

mapper = Path("web/src/features/integration/register-marketplace-props.tsx")
text = mapper.read_text(encoding="utf-8")
helper_anchor = '''const numberValue = (value: unknown): number | null => {
  if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};
'''
helper_replacement = helper_anchor + '''
const httpsUrlValue = (value: unknown): string => {
  const normalized = stringValue(value);
  if (!normalized) return "";
  try {
    const parsed = new URL(normalized);
    return parsed.protocol === "https:" && parsed.hostname ? normalized : "";
  } catch {
    return "";
  }
};

const catalogIntegrityError = (message: string): Error => new Error(`Catalog integrity error: ${message}`);
'''
if text.count(helper_anchor) != 1:
    raise SystemExit(f"number helper anchors: {text.count(helper_anchor)}")
text = text.replace(helper_anchor, helper_replacement, 1)

pattern = re.compile(
    r'''export const mapCatalogIndex = \(index: unknown\): MarketplaceProduct\[\] => \{.*?\n\};\n\nconst detailProduct =''',
    re.S,
)
replacement = '''export const mapCatalogIndex = (index: unknown): MarketplaceProduct[] => {
  const envelope = objectValue(index);
  if (!envelope || !Array.isArray(envelope.products)) {
    throw catalogIntegrityError("products must be an array");
  }
  const rows = envelope.products;
  const declaredProductCount = numberValue(envelope.product_count);
  const declaredVariantCount = numberValue(envelope.in_stock_variant_count);
  if (declaredProductCount !== null && declaredProductCount !== rows.length) {
    throw catalogIntegrityError(`product count mismatch: declared ${declaredProductCount}, received ${rows.length}`);
  }

  const productIds = new Set<string>();
  const variantIds = new Set<string>();
  let mappedVariantCount = 0;
  const products = rows.map((raw, productIndex): MarketplaceProduct => {
    const product = objectValue(raw);
    if (!product) throw catalogIntegrityError(`catalog product ${productIndex} must be an object`);
    const id = stringValue(product.product_id);
    const vendorId = stringValue(product.vendor_id);
    const vendorName = stringValue(product.vendor_name);
    const strainName = stringValue(product.strain_name);
    if (!id) throw catalogIntegrityError(`catalog product ${productIndex} is missing product_id`);
    if (productIds.has(id)) throw catalogIntegrityError(`duplicate catalog product: ${id}`);
    productIds.add(id);
    if (!vendorId) throw catalogIntegrityError(`catalog product ${id} is missing vendor_id`);
    if (!vendorName) throw catalogIntegrityError(`catalog product ${id} is missing vendor_name`);
    if (!strainName) throw catalogIntegrityError(`catalog product ${id} is missing strain_name`);
    if (!Array.isArray(product.variants) || product.variants.length === 0) {
      throw catalogIntegrityError(`catalog product ${id} has no variants`);
    }

    const variants = product.variants.map((rawVariant, variantIndex): MarketplaceVariant => {
      const variant = objectValue(rawVariant);
      if (!variant) throw catalogIntegrityError(`catalog variant ${id}:${variantIndex} must be an object`);
      const variantId = stringValue(variant.variant_id);
      if (!variantId) throw catalogIntegrityError(`catalog variant ${id}:${variantIndex} is missing variant_id`);
      if (variantIds.has(variantId)) throw catalogIntegrityError(`duplicate catalog variant: ${variantId}`);
      variantIds.add(variantId);
      if (variant.in_stock !== true) throw catalogIntegrityError(`catalog variant ${variantId} is not explicitly in stock`);
      const grams = numberValue(variant.grams);
      const currentPrice = numberValue(variant.current_price);
      const pricePerGram = numberValue(variant.price_per_gram);
      const productUrl = httpsUrlValue(variant.product_url);
      if (grams === null || grams <= 0) throw catalogIntegrityError(`catalog variant ${variantId} has invalid grams`);
      if (currentPrice === null || currentPrice <= 0) throw catalogIntegrityError(`catalog variant ${variantId} has invalid price`);
      if (pricePerGram === null || pricePerGram <= 0) throw catalogIntegrityError(`catalog variant ${variantId} has invalid price per gram`);
      if (!productUrl) throw catalogIntegrityError(`catalog variant ${variantId} has invalid product URL`);
      mappedVariantCount += 1;
      return {
        id: variantId,
        grams,
        sourceWeightLabel: stringValue(variant.source_weight_label) || `${grams} g`,
        currentPrice,
        originalPrice: numberValue(variant.original_price),
        pricePerGram,
        inStock: true,
        productUrl,
        imageUrl: stringValue(variant.image_url) || null,
        coa: selectDocument(variant.documents, "coa"),
        terpeneDocument: selectDocument(variant.documents, "terpene"),
      };
    });

    const lineage = stringValue(product.lineage);
    return {
      id,
      vendorId,
      vendorName,
      vendorFaviconUrl: stringValue(product.vendor_favicon_url) || null,
      strainName,
      lineage: [
        "indica",
        "indica_leaning_hybrid",
        "hybrid",
        "sativa_leaning_hybrid",
        "sativa",
      ].includes(lineage) ? lineage as MarketplaceProduct["lineage"] : "unknown",
      totalThcDisplay: numberValue(product.total_thc_display_percent ?? product.total_thc),
      rating: numberValue(product.rating),
      reviewCount: numberValue(product.review_count),
      variants,
    };
  });

  if (declaredVariantCount !== null && declaredVariantCount !== mappedVariantCount) {
    throw catalogIntegrityError(`variant count mismatch: declared ${declaredVariantCount}, mapped ${mappedVariantCount}`);
  }
  return products;
};

const detailProduct ='''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"mapCatalogIndex replacements: {count}")
mapper.write_text(text, encoding="utf-8")
