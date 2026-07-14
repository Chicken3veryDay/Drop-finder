from __future__ import annotations

import uuid
from typing import Any, Literal

from app.reliability.contracts import AdapterDefinition, AdapterState, StrategyType
from app.reliability.store import ReliabilityStore


class AdapterRegistry:
    def __init__(self, store: ReliabilityStore):
        self.store = store

    def create(
        self,
        *,
        source_id: str,
        route_id: str,
        strategy_type: StrategyType,
        config: dict[str, Any],
        parent_adapter_id: str = "",
        change_set: list[dict[str, Any]] | None = None,
        generated_by: Literal["manual", "deterministic_repair", "migration"] = "manual",
        evidence_ids: list[str] | None = None,
    ) -> AdapterDefinition:
        versions = self.store.list_adapters(source_id, route_id)
        version = max((int(item["version"]) for item in versions), default=0) + 1
        adapter = AdapterDefinition(
            adapter_id=f"{source_id}:{route_id}:v{version}:{uuid.uuid4().hex[:8]}",
            source_id=source_id,
            route_id=route_id,
            version=version,
            parent_adapter_id=parent_adapter_id,
            strategy_type=strategy_type,
            state=AdapterState.CANDIDATE,
            config=config,
            change_set=tuple(change_set or []),
            generated_by=generated_by,
            evidence_ids=tuple(evidence_ids or []),
        )
        return self.store.register_adapter(adapter)

    def migrate_profile(
        self, source_profile: dict[str, Any], route: dict[str, Any]
    ) -> AdapterDefinition:
        source_id = str(source_profile.get("id") or "")
        route_id = str(route.get("route_id") or route.get("id") or "primary")
        source_type = str(
            route.get("source_type") or source_profile.get("source_type") or "html"
        )
        strategy = {
            "shopify_json": StrategyType.JSON_ENDPOINT,
            "woocommerce_store_api": StrategyType.JSON_ENDPOINT,
            "dutchie_graphql": StrategyType.OFFICIAL_API,
            "sitemap_products": StrategyType.SITEMAP,
            "html": StrategyType.HTML_CARDS,
            "auto": StrategyType.HTML_CARDS,
        }.get(source_type, StrategyType.HTML_CARDS)
        config = {
            "source_url": str(
                route.get("source_url")
                or route.get("url")
                or source_profile.get("source_url")
                or ""
            ),
            "source_type": source_type,
            "selectors": route.get("selectors")
            or source_profile.get("selectors")
            or {},
            "max_pages": int(
                route.get("max_pages") or source_profile.get("max_pages") or 12
            ),
            "allowed_origins": route.get("allowed_origins")
            or source_profile.get("allowed_origins")
            or [],
        }
        return self.create(
            source_id=source_id,
            route_id=route_id,
            strategy_type=strategy,
            config=config,
            generated_by="migration",
        )
