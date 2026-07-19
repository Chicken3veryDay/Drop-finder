from pathlib import Path

path = Path("scripts/catalog_v4/verify.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one anchor, found {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


replace_once(
'''def _verify_bytes(path:Path,meta:dict[str,Any],*,label:str,maximum:int|None=None,required:bool=False)->int:
    actual=path.stat().st_size;declared=meta.get("bytes")
    if required and (not isinstance(declared,int) or declared<0):raise VerificationError(f"{label} missing declared bytes: {path}")
    if declared is not None and declared!=actual:raise VerificationError(f"{label} byte count mismatch: {path}")
    if maximum is not None and actual>maximum:raise VerificationError(f"{label} exceeds browser byte limit: {path}")
    return actual
''',
'''def _verify_bytes(
    path: Path,
    meta: dict[str, Any],
    *,
    label: str,
    maximum: int | None = None,
    required: bool = False,
    check_declared: bool = True,
) -> int:
    actual = path.stat().st_size
    declared = meta.get("bytes")
    if required and (not isinstance(declared, int) or declared < 0):
        raise VerificationError(f"{label} missing declared bytes: {path}")
    if maximum is not None and actual > maximum:
        raise VerificationError(f"{label} exceeds browser byte limit: {path}")
    if check_declared and declared is not None and declared != actual:
        raise VerificationError(f"{label} byte count mismatch: {path}")
    return actual
''')

replace_once(
'''    _verify_bytes(index_path,index_meta,label="compact index",maximum=MAX_INDEX_BYTES,required=required)
''',
'''    _verify_bytes(
        index_path,
        index_meta,
        label="compact index",
        maximum=MAX_INDEX_BYTES,
        required=required,
        check_declared=False,
    )
''')
replace_once(
'''    _verify_bytes(vendors_path,vendors_meta,label="vendor profile",required=required)
''',
'''    _verify_bytes(
        vendors_path,
        vendors_meta,
        label="vendor profile",
        required=required,
        check_declared=False,
    )
''')
replace_once(
'''    _verify_bytes(rejections_path,rejections_meta,label="rejections",required=required)
''',
'''    _verify_bytes(
        rejections_path,
        rejections_meta,
        label="rejections",
        required=required,
        check_declared=False,
    )
''')
replace_once(
'''    detail_product_ids: set[str] = set()
    declared_detail_count = 0
''',
'''    detail_product_ids: set[str] = set()
    detail_byte_checks: list[tuple[Path, dict[str, Any]]] = []
    declared_detail_count = 0
''')
replace_once(
'''        _verify_bytes(path,entry,label="detail shard",maximum=MAX_DETAIL_BYTES,required=required)
''',
'''        _verify_bytes(
            path,
            entry,
            label="detail shard",
            maximum=MAX_DETAIL_BYTES,
            required=required,
            check_declared=False,
        )
        detail_byte_checks.append((path, entry))
''')
replace_once(
'''    if manifest.get("vendor_count") != vendors.get("vendor_count"):
        raise VerificationError("vendor count mismatch")
    return {
''',
'''    if manifest.get("vendor_count") != vendors.get("vendor_count"):
        raise VerificationError("vendor count mismatch")

    # Descriptor byte parity is a final consistency check. Hard browser ceilings
    # were enforced before parsing, while hash/schema/identity failures remain the
    # primary diagnostic when a test or publication intentionally mutates content.
    _verify_bytes(index_path, index_meta, label="compact index", maximum=MAX_INDEX_BYTES, required=required)
    _verify_bytes(vendors_path, vendors_meta, label="vendor profile", required=required)
    _verify_bytes(rejections_path, rejections_meta, label="rejections", required=required)
    for detail_path, detail_meta in detail_byte_checks:
        _verify_bytes(
            detail_path,
            detail_meta,
            label="detail shard",
            maximum=MAX_DETAIL_BYTES,
            required=required,
        )
    return {
''')

path.write_text(text, encoding="utf-8")
