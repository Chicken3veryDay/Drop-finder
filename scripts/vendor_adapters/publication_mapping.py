"""Convert vendor document candidates into Catalog V4 document records."""
from __future__ import annotations

from typing import Any

from .mapping import map_documents
from .models import DocumentCandidate, MappingDecision
from .publication_common import (
    product_id,
    product_url,
    source_product_id,
    source_variant_id,
    vendor_id,
)


def _kind(value: str) -> str:
    return {
        "coa": "coa",
        "terpene_report": "terpene",
        "combined_lab_report": "combined",
    }.get(str(value or ""), "unknown")


def _target_index(products: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    output: dict[tuple[str, str, str], dict[str, Any]] = {}
    for product in products:
        key = (vendor_id(product), product_id(product), source_variant_id(product))
        if key[0] and key[1]:
            output[key] = product
    return output
