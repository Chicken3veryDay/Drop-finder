from __future__ import annotations

import math
from typing import Any

import render_deploy

CONTRACT = "exact_price_weight_ppg_thca_stock_image_v1"
EXACT_PRICING = {"exact_variant", "exact_title"}
KNOWN_STOCK = {"in_stock", "out_of_stock"}
_original_verify_catalog = render_deploy.verify_catalog


def positive(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def product_failures(product: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    price = positive(product.get("price"))
    grams = positive(product.get("grams"))
    price_per_gram = positive(product.get("price_per_gram"))
    thca = positive(product.get("thca"))
    if product.get("comparison_complete") is not True:
        failures.append("comparison_complete")
    if product.get("comparison_contract") != CONTRACT:
        failures.append("comparison_contract")
    if price is None:
        failures.append("price")
    if grams is None:
        failures.append("grams")
    if price_per_gram is None:
        failures.append("price_per_gram")
    if product.get("pricing_confidence") not in EXACT_PRICING:
        failures.append("pricing_confidence")
    if product.get("weight_source") not in {"variant", "title"}:
        failures.append("weight_source")
    if price is not None and grams is not None and price_per_gram is not None:
        calculated = round(price / grams, 4)
        if abs(calculated - price_per_gram) > max(0.02, calculated * 0.01):
            failures.append("price_per_gram_arithmetic")
    if thca is None or thca > 100:
        failures.append("thca")
    if product.get("availability") not in KNOWN_STOCK:
        failures.append("availability")
    if not str(product.get("image") or "").startswith(("http://", "https://")):
        failures.append("image")
    if not str(product.get("url") or "").startswith(("http://", "https://")):
        failures.append("url")
    return failures


def verify_catalog(app_url: str) -> dict[str, Any]:
    verified = _original_verify_catalog(app_url)
    catalog = verified["catalog"]
    source_status = verified["status"]
    runtime = verified["runtime"]
    products = catalog.get("products") or []

    if catalog.get("comparison_contract") != CONTRACT:
        raise RuntimeError(f"unexpected catalog comparison contract: {catalog.get('comparison_contract')}")
    if source_status.get("comparison_contract") != CONTRACT:
        raise RuntimeError(f"unexpected status comparison contract: {source_status.get('comparison_contract')}")
    if runtime.get("comparison_contract") != CONTRACT:
        raise RuntimeError(f"unexpected runtime comparison contract: {runtime.get('comparison_contract')}")
    if source_status.get("complete_products") != len(products):
        raise RuntimeError("status complete-product count mismatch")
    if runtime.get("complete_products") != len(products):
        raise RuntimeError("runtime complete-product count mismatch")
    if source_status.get("services", {}).get("comparison_completeness_gate") != "healthy":
        raise RuntimeError("comparison completeness gate is not healthy")

    failures = []
    for product in products:
        failed = product_failures(product)
        if failed:
            failures.append({"id": product.get("id"), "source_id": product.get("source_id"), "failed": failed})
    if failures:
        raise RuntimeError(f"hosted complete-product contract failed for {len(failures)} rows: {failures[:10]}")

    verified["completeness"] = {
        "contract": CONTRACT,
        "complete_products": len(products),
        "field_failure_count": 0,
        "sources": source_status.get("healthy_sources"),
    }
    return verified


def apply() -> None:
    render_deploy.verify_catalog = verify_catalog
