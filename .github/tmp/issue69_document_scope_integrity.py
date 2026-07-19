from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


builder = "scripts/catalog_v4/builder.py"
replace_once(
    builder,
    '''            source_variant_id = clean_text(raw.get("source_variant_id") or raw.get("variant_id"))
            documents = normalize_documents(
                combined_documents,
                product_id=product_id,
                vendor_id=source_id,
                variant_id=variant_id,
                source_variant_id=source_variant_id,
                grams=float(grams),
            )
            variant = {
''',
    '''            source_variant_id = clean_text(raw.get("source_variant_id") or raw.get("variant_id"))
            target_batch = clean_text(raw.get("batch"))
            target_lot = clean_text(raw.get("lot"))
            documents = normalize_documents(
                combined_documents,
                product_id=product_id,
                vendor_id=source_id,
                variant_id=variant_id,
                source_variant_id=source_variant_id,
                grams=float(grams),
                batch=target_batch,
                lot=target_lot,
                rejections=rejections,
            )
            variant = {
''',
)
replace_once(
    builder,
    '''                "documents": documents,
                "batch": clean_text(raw.get("batch")),
                "lot": clean_text(raw.get("lot")),
''',
    '''                "documents": documents,
                "batch": target_batch,
                "lot": target_lot,
''',
)

verify = "scripts/catalog_v4/verify.py"
replace_once(
    verify,
    '''                    if str(document.get("product_id") or "") != product_id:
                        raise VerificationError(f"document product mismatch: {product_id}")
''',
    '''                    if str(document.get("product_id") or "") != product_id:
                        raise VerificationError(f"document product mismatch: {product_id}")
                    scope = str(document.get("scope") or "")
                    if scope not in {"variant", "weight", "batch", "product", "vendor"}:
                        raise VerificationError(f"document invalid scope: {product_id} {variant_id}")
                    document_variant_id = str(document.get("variant_id") or "")
                    if scope in {"variant", "weight", "batch"}:
                        if document_variant_id != variant_id:
                            raise VerificationError(f"document variant identity mismatch: {product_id} {variant_id}")
                    elif document_variant_id:
                        raise VerificationError(f"broad document has variant identity: {product_id} {variant_id}")
                    if scope == "variant":
                        source_identity = str(document.get("source_variant_id") or "")
                        target_source_identity = str(variant.get("source_variant_id") or "")
                        if not source_identity or source_identity not in {variant_id, target_source_identity}:
                            raise VerificationError(f"document source variant identity mismatch: {product_id} {variant_id}")
                    elif scope == "weight":
                        try:
                            document_grams = float(document["grams"])
                            variant_grams = float(variant["grams"])
                        except (KeyError, TypeError, ValueError) as exc:
                            raise VerificationError(f"document weight identity missing: {product_id} {variant_id}") from exc
                        if abs(document_grams - variant_grams) > 0.01:
                            raise VerificationError(f"document weight identity mismatch: {product_id} {variant_id}")
                    elif scope == "batch":
                        document_batches = {
                            normalized
                            for value in (document.get("batch"), document.get("lot"))
                            if (normalized := str(value or "").strip().casefold())
                        }
                        variant_batches = {
                            normalized
                            for value in (variant.get("batch"), variant.get("lot"))
                            if (normalized := str(value or "").strip().casefold())
                        }
                        if not document_batches or not variant_batches or document_batches.isdisjoint(variant_batches):
                            raise VerificationError(f"document batch identity mismatch: {product_id} {variant_id}")
''',
)
