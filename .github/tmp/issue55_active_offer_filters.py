from pathlib import Path

path = Path("web/src/platform/workers/marketplace-query-engine.js")
text = path.read_text(encoding="utf-8")

old = '''    const variant = chooseVariant(product.variants, request.minWeight, request.maxWeight, request.minPrice, request.maxPrice, request.minPpg, request.maxPpg);
    if (!variant) continue;
    selected.push(projectRow(product, variant));
'''
new = '''    const variant = chooseVariant(product.variants, request.minWeight, request.maxWeight);
    if (!variant) continue;
    if (!between(variant.price, request.minPrice, request.maxPrice)) continue;
    if (!between(variant.ppg, request.minPpg, request.maxPpg)) continue;
    selected.push(projectRow(product, variant));
'''
if text.count(old) != 1:
    raise SystemExit(f"executeQuery anchor count: {text.count(old)}")
text = text.replace(old, new, 1)

old = '''function chooseVariant(variants, minWeight, maxWeight, minPrice, maxPrice, minPpg, maxPpg) {
  let best = null;
  for (const variant of variants) {
    if (!between(variant.weight, minWeight, maxWeight)) continue;
    if (!between(variant.price, minPrice, maxPrice)) continue;
    if (!between(variant.ppg, minPpg, maxPpg)) continue;
    if (!best || compareVariant(variant, best) < 0) best = variant;
  }
  return best;
}
'''
new = '''function chooseVariant(variants, minWeight, maxWeight) {
  let best = null;
  for (const variant of variants) {
    if (!between(variant.weight, minWeight, maxWeight)) continue;
    if (!best || compareVariant(variant, best) < 0) best = variant;
  }
  return best;
}
'''
if text.count(old) != 1:
    raise SystemExit(f"chooseVariant anchor count: {text.count(old)}")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
