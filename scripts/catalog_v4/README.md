# DropFinder catalog v4 generator

This package converts the already-admitted strict-flower catalog into the
shopper-facing v4 contract. It does not scrape storefronts and it does not
weaken the existing flower classifier. Its boundary starts after source
admission and ends with hash-verified static files.

```bash
python -m scripts.catalog_v4 \
  --input cloud_pages/data/catalog.json \
  --output cloud_pages/data \
  --detail-shards 16

python -m scripts.catalog_v4 --input cloud_pages/data/catalog.json \
  --output cloud_pages/data --verify-only
```

The output root contains `catalog-v4/manifest.json`, `index.json`,
`vendors.json`, `rejections.json`, and deterministic detail shards under
`catalog-v4/details/`.
