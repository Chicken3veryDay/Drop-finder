const LINEAGES = ['indica', 'indica_hybrid', 'hybrid', 'sativa_hybrid', 'sativa', 'unknown'];
const WEIGHTS = [3.5, 7, 14, 28];

/** Deterministic catalog fixtures shared by unit, benchmark, and browser tests. */
export function createSyntheticCatalog(count, options = {}) {
  const seed = Number(options.seed ?? 0xD09F1D3) >>> 0;
  const random = mulberry32(seed);
  const vendorCount = Math.max(1, Number(options.vendorCount ?? 37));
  const includeDocuments = options.includeDocuments !== false;
  const products = new Array(count);
  for (let index = 0; index < count; index += 1) {
    const vendorIndex = index % vendorCount;
    const totalThc = Number((10 + random() * 30).toFixed(2));
    const id = `p-${String(index).padStart(6, '0')}`;
    products[index] = Object.freeze({
      id,
      product_id: id,
      vendor_id: `vendor-${vendorIndex}`,
      source_id: `vendor-${vendorIndex}`,
      vendor: `Vendor ${String(vendorIndex).padStart(2, '0')}`,
      strain: `Strain ${String(index % 997).padStart(3, '0')}`,
      name: `Strain ${String(index % 997).padStart(3, '0')}`,
      lineage: LINEAGES[index % LINEAGES.length],
      total_thc: totalThc,
      image: index % 4 ? `https://fixtures.invalid/products/${index}.webp` : null,
      detail_shard: `details/${String(index % 128).padStart(3, '0')}.json`,
      documents: includeDocuments && index % 5 === 0 ? [{ id: `coa-${id}`, type: 'coa', url: './sample.pdf', mimeType: 'application/pdf' }] : [],
      variants: WEIGHTS.map((weight, variantIndex) => {
        const ppg = Number((3 + ((index + variantIndex) % 13) / 3).toFixed(4));
        return Object.freeze({
          id: `${id}-v${variantIndex}`,
          variant_id: `${id}-v${variantIndex}`,
          grams: weight,
          weight,
          price: Number((weight * ppg).toFixed(2)),
          price_per_gram: ppg,
        });
      }),
    });
  }
  return Object.freeze(products);
}

export function createCatalogEnvelope(count, options = {}) {
  const generationId = String(options.generationId ?? `fixture-${count}`);
  return Object.freeze({
    schema_version: 4,
    generation_id: generationId,
    products: createSyntheticCatalog(count, options),
  });
}

function mulberry32(seed) {
  return function random() {
    let value = seed += 0x6D2B79F5;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}
