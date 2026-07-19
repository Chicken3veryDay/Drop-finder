from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


normalization = "scripts/catalog_v4/normalization.py"
replace_once(
    normalization,
    '''MARKETING_SUFFIX = re.compile(
    r"\\s*[|\\-–—_:]+\\s*(?:limited\\s+drop|new\\s+drop|best\\s+seller|staff\\s+pick|exotic|premium|sale)\\s*$",
    re.I,
)
''',
    '''MARKETING_SUFFIX = re.compile(
    r"\\s*[|\\-–—_:]+\\s*(?:limited\\s+drop|new\\s+drop|best\\s+seller|staff\\s+pick|exotic|premium|sale)\\s*$",
    re.I,
)
_NAME_SUFFIX_BOUNDARY = r"(?:\\s*[|\\-–—_:]+\\s*|\\s+)"
COMPOSABLE_NAME_SUFFIXES = (
    re.compile(_NAME_SUFFIX_BOUNDARY + r"tier\\s+\\d+\\s*$", re.I),
    re.compile(_NAME_SUFFIX_BOUNDARY + r"(?:smalls|minis|small\\s+buds|premium\\s+buds|whole\\s+flower)\\s*$", re.I),
    re.compile(_NAME_SUFFIX_BOUNDARY + r"(?:indoor|outdoor|greenhouse|mixed\\s+light)\\s*$", re.I),
    re.compile(_NAME_SUFFIX_BOUNDARY + r"(?:limited\\s+drop|new\\s+drop|best\\s+seller|staff\\s+pick|exotic|premium|sale)\\s*$", re.I),
    re.compile(_NAME_SUFFIX_BOUNDARY + r"(?:premium\\s+)?(?:high\\s+)?thc-?a(?:\\s+(?:hemp\\s+)?flower)?\\s*$", re.I),
    re.compile(_NAME_SUFFIX_BOUNDARY + r"(?:hemp\\s+)?flower\\s*$", re.I),
)
''',
)
replace_once(
    normalization,
    '''    while title and title != previous:
        previous = title
        for pattern in TRAILING_NAME_PATTERNS:
            title = pattern.sub("", title).strip(" |-_–—:")
        title = MARKETING_SUFFIX.sub("", title).strip(" |-_–—:")
    return title or clean_text(source_title)
''',
    '''    while title and title != previous:
        previous = title
        for pattern in (*COMPOSABLE_NAME_SUFFIXES, *TRAILING_NAME_PATTERNS):
            candidate = pattern.sub("", title).strip(" |-_–—:")
            if candidate:
                title = candidate
        candidate = MARKETING_SUFFIX.sub("", title).strip(" |-_–—:")
        if candidate:
            title = candidate
    return title or clean_text(source_title)
''',
)

builder = "scripts/catalog_v4/builder.py"
replace_once(
    builder,
    '''def _merge_product_field(records: list[dict[str, Any]], key: str) -> Any:
    ranked = sorted(
        records,
        key=lambda row: (
            row.get(key) not in (None, "", [], {}),
            clean_text(row.get("collected_at")),
            sum(row.get(field) not in (None, "", [], {}) for field in row),
        ),
        reverse=True,
    )
    return ranked[0].get(key) if ranked else None



''',
    '''def _merge_product_field(records: list[dict[str, Any]], key: str) -> Any:
    ranked = sorted(
        records,
        key=lambda row: (
            row.get(key) not in (None, "", [], {}),
            clean_text(row.get("collected_at")),
            sum(row.get(field) not in (None, "", [], {}) for field in row),
        ),
        reverse=True,
    )
    return ranked[0].get(key) if ranked else None


def _select_rating_pair(records: list[dict[str, Any]]) -> tuple[float | None, int | None, dict[str, Any]]:
    candidates: list[tuple[tuple[str, int, str], float, int, dict[str, Any]]] = []
    for row in records:
        score, count, provenance = rating(row.get("rating"), row.get("review_count"))
        if score is None or count is None:
            continue
        source_record_id = clean_text(row.get("source_record_id")) or stable_digest(
            row.get("source_id"),
            row.get("url"),
            row.get("source_variant_id"),
            row.get("collected_at"),
            length=20,
        )
        pair_provenance = {
            **provenance,
            "method": "atomic_source_record_pair",
            "source_record_id": source_record_id,
            "source_path": canonical_url(row.get("route_url") or row.get("url"), keep_variant=True),
            "collected_at": clean_text(row.get("collected_at")),
        }
        rank = (
            clean_text(row.get("collected_at")),
            sum(row.get(field) not in (None, "", [], {}) for field in row),
            source_record_id,
        )
        candidates.append((rank, score, count, pair_provenance))
    if not candidates:
        return rating(None, None)
    _, score, count, provenance = max(candidates, key=lambda candidate: candidate[0])
    return score, count, provenance


''',
)
replace_once(
    builder,
    '''                product_identity_provenance=identity_provenance,
            )
''',
    '''                product_identity_provenance=identity_provenance,
                source_record_id=source_record_id,
            )
''',
)
replace_once(
    builder,
    '''            effect_values, effects_provenance = effects(_merge_product_field(records_for_product, "effects"))
            rating_value, review_count, rating_provenance = rating(
                _merge_product_field(records_for_product, "rating"),
                _merge_product_field(records_for_product, "review_count"),
            )
''',
    '''            effect_values, effects_provenance = effects(_merge_product_field(records_for_product, "effects"))
            rating_value, review_count, rating_provenance = _select_rating_pair(records_for_product)
''',
)
replace_once(
    builder,
    '''            products.append(
                {
''',
    '''            selected_strain_name = min(
                (clean_text(row.get("canonical_strain_name")) for row in records_for_product if clean_text(row.get("canonical_strain_name"))),
                key=lambda value: (len(value), value.casefold()),
            )
            products.append(
                {
''',
)
replace_once(
    builder,
    '''                    "strain_name": min(
                        (clean_text(row.get("canonical_strain_name")) for row in records_for_product if clean_text(row.get("canonical_strain_name"))),
                        key=lambda value: (len(value), value.casefold()),
                    ),
''',
    '''                    "strain_name": selected_strain_name,
''',
)
replace_once(
    builder,
    '''                        "strain": normalized_search(seed["canonical_strain_name"]),
''',
    '''                        "strain": normalized_search(selected_strain_name),
''',
)

verify = "scripts/catalog_v4/verify.py"
replace_once(
    verify,
    '''    index_variants_by_product: dict[str, dict[str, tuple[float, str]]] = {}
''',
    '''    index_variants_by_product: dict[str, dict[str, tuple[float, str]]] = {}
    index_ratings_by_product: dict[str, tuple[Any, Any]] = {}
''',
)
replace_once(
    verify,
    '''        if product.get("lineage") not in allowed_lineages:
            raise VerificationError(f"invalid lineage: {product_id}")
        variants = product.get("variants")
''',
    '''        if product.get("lineage") not in allowed_lineages:
            raise VerificationError(f"invalid lineage: {product_id}")
        rating_value = product.get("rating")
        review_count = product.get("review_count")
        if (rating_value is None) != (review_count is None):
            raise VerificationError(f"rating/count nullability mismatch: {product_id}")
        index_ratings_by_product[product_id] = (rating_value, review_count)
        variants = product.get("variants")
''',
)
replace_once(
    verify,
    '''            product_urls.add(url_key)
            variants = product.get("variants")
''',
    '''            product_urls.add(url_key)
            rating_value = product.get("rating")
            review_count = product.get("review_count")
            if (rating_value, review_count) != index_ratings_by_product.get(product_id):
                raise VerificationError(f"index/detail rating mismatch: {product_id}")
            rating_provenance = product.get("rating_provenance")
            if rating_value is None:
                if review_count is not None:
                    raise VerificationError(f"detail rating/count nullability mismatch: {product_id}")
                if not isinstance(rating_provenance, dict) or rating_provenance.get("source") != "unavailable":
                    raise VerificationError(f"invalid unavailable rating provenance: {product_id}")
            else:
                if not isinstance(rating_provenance, dict):
                    raise VerificationError(f"missing rating provenance: {product_id}")
                if rating_provenance.get("method") != "atomic_source_record_pair":
                    raise VerificationError(f"non-atomic rating provenance: {product_id}")
                for field in ("source_record_id", "source_path", "collected_at"):
                    if not str(rating_provenance.get(field) or "").strip():
                        raise VerificationError(f"rating provenance missing {field}: {product_id}")
            variants = product.get("variants")
''',
)
