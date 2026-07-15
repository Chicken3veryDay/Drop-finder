# Catalog v4 production integration and rollback

## Upstream boundary

The v4 builder consumes `cloud_pages/data/catalog.json` only after the existing
autonomous worker and strict-flower sanitizer have admitted products. It is a
shopper-data transformation, not another classifier. This separation preserves
the current safety gate while allowing the UI schema to evolve independently.

Optional vendor input may be supplied as either a `vendors` list or a map keyed
by `vendor_id`. Fields used by issue #6 are:

- `vendor_id`
- `vendor_name`
- `favicon_url` and optional favicon provenance
- `age_gate_classification`
- `age_gate_evidence_reference`

This is the narrow consumer contract for the vendor-document workstream in
issue #7. Missing profiles generate a minimal vendor record with an uncertain
age-gate classification rather than fabricated data.

Optional document input may be a list or `{ "documents": [...] }`. Documents
map by source product ID, normalized product ID, or canonical product URL.

## Build and verify

```bash
python -m compileall -q scripts/catalog_v4 tests/catalog_v4
python -m scripts.catalog_v4.selftest
python -m unittest discover -s tests/catalog_v4 -v
python -m scripts.catalog_v4 \
  --input cloud_pages/data/catalog.json \
  --output /tmp/dropfinder-catalog-v4 \
  --detail-shards 16 \
  --minimum-products 1 \
  --minimum-variants 1
```

The CLI builds all files, enforces publication floors, writes through temporary
files, and then verifies hashes, generation IDs, counts, product/variant
identity, unique weights, stock state, prices, discount math, active-variant
selection, lineage values, canonical product URLs, and detail/index parity.

## GitHub Actions publication

`.github/workflows/catalog-v4.yml` runs the package tests on pull requests and
package changes. It also runs after a successful `DropFinder Autonomous Cloud`
workflow. The publish job:

1. Checks out the latest `main` snapshot.
2. Builds and verifies v4 in a temporary directory.
3. Replaces only `cloud_pages/data/catalog-v4`.
4. Commits the verified generation to `main`.
5. Copies the same verified bytes into the existing `gh-pages` site.
6. Re-verifies the published worktree before pushing.

The v4 data path is deliberately absent from the workflow's own push trigger,
preventing publication loops.

## Client loading contract

1. Load `data/catalog-v4/manifest.json` with cache bypass or revalidation.
2. Load and hash-check the compact index and vendor profile files.
3. Render the marketplace from the compact index.
4. Fetch a detail shard only when a product is expanded.
5. Reject a detail shard if its generation ID differs from the loaded index.
6. On the next manifest generation, atomically replace client state rather than
   mixing old and new files.

## Rollback

The existing v3 `data/catalog.json` remains untouched and is declared in the
manifest as the read-only rollback input. To roll back v4 only:

1. Revert the v4 publication commit on `main`.
2. Restore the corresponding `data/catalog-v4` directory on `gh-pages`, or let
   the next successful catalog-v4 workflow republish it.
3. Keep the UI on the v3 loader until the corrected v4 generation passes the
   verifier.

No database migration is required. Product and variant IDs are content-derived,
so a corrected build remains deterministic for unchanged source identities.
