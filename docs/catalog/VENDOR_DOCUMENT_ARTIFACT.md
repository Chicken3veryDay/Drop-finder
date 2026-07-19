# Vendor document publication artifact

Catalog V4 accepts laboratory documents only through a versioned intermediate artifact. The artifact keeps source discovery separate from product attachment so unsupported or ambiguous evidence remains visible without being guessed onto a shopper record.

## Source registry

`data/vendor_document_sources.json` uses schema `dropfinder-vendor-document-sources-v1`.

Each source identifies:

- the canonical DropFinder `vendor_id`;
- the first-party source page;
- the observation time;
- every public document URL, explicit source label, MIME type, and document kind.

Document hosts must be allowed by the corresponding profile in `data/vendor_profiles.json`. The checked-in source registry is evidence, not a declaration that every report belongs to a currently published product.

## Generated artifact

Run:

```bash
python -m scripts.vendor_adapters.publication_artifact \
  --catalog cloud_pages/data/catalog.json \
  --vendor-profiles data/vendor_profiles.json \
  --sources data/vendor_document_sources.json \
  --output /tmp/vendor-documents.json
```

The output uses schema `dropfinder-vendor-document-artifact-v1` and contains:

- `documents`: uniquely mapped, builder-ready product-scoped records;
- `unmatched_documents`: every report that could not be safely mapped, with a stable reason;
- `source_statuses`: per-vendor accounting and reason counts;
- `counts`: source, mapped, unmatched, and vendor totals.

Every source document must appear exactly once in either `documents` or `unmatched_documents`.

## Mapping rule

Automatic mapping is intentionally narrow:

1. vendor identity must exist in the validated vendor registry;
2. source and document URLs must remain on declared hosts;
3. document kind and label must be explicit;
4. the normalized source label must match exactly one catalog product for the same vendor;
5. ambiguous or absent products remain unmatched.

No substring, lowest-distance, weight-only, price, traversal-order, or vendor-level fallback can create a product association.

## Publication

`.github/workflows/catalog-v4.yml` always:

1. builds the document artifact;
2. verifies complete source accounting;
3. passes it through `--documents` to Catalog V4;
4. verifies the resulting publication;
5. uploads both the catalog and the document artifact.

A report can become mapped automatically in a later generation when an exact unique catalog identity appears. The source evidence does not need to be deleted or rewritten, and unmatched history remains auditable.
