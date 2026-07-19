# Strict JSON publication contract

DropFinder accepts and publishes interoperable JSON only.

## Input boundaries

CLI input and optional catalog input files reject the non-standard constants `NaN`, `Infinity`, and `-Infinity`. Parsing failures stop the generation before public artifacts are written.

## Recursive value boundary

Before serialization, every nested object, array, tuple, provenance record, document record, and detail shard is checked recursively. Object keys must be strings. Floating-point values must be finite. Unsupported Python values are rejected rather than stringified implicitly.

Optional raw provenance may preserve ordinary scalar, object, and list evidence. Non-finite optional numbers are represented as `null`; they are never emitted as browser-invalid numeric tokens or converted into invented finite values.

## Serialization and verification

Canonical generation bytes and human-readable public artifacts use the same strict serializer with `allow_nan=false`. Publication verification parses generated JSON through the strict parser even when a file's hash matches its manifest entry, preventing a hash-consistent but browser-invalid shard from passing verification.

Any new JSON input, cache, generated artifact, manifest, compact index, detail shard, provenance export, or verification path must use `scripts.catalog_v4.strict_json` or an equivalently tested standards-compatible boundary.
