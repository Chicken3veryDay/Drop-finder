from __future__ import annotations

import re

from scripts import route_repair


class Core:
    SOURCES = [
        (
            "bay_smokes",
            "Bay Smokes",
            [("html", "https://bay-smokes.com/collections/thca-flower", "thca_flower")],
        ),
        ("fixture", "Fixture", [("html", "https://example.test/old", "storewide")]),
    ]
    LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
    ANCHOR = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)

    @staticmethod
    def text(value):
        return " ".join(re.sub(r"<[^>]+>", " ", str(value or "")).split())

    @staticmethod
    def num(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def availability(value):
        value = str(value or "").casefold()
        if "instock" in value.replace("_", "") or "in stock" in value or "add to cart" in value:
            return "in_stock"
        if "outofstock" in value.replace("_", "") or "out of stock" in value:
            return "out_of_stock"
        return "unknown"

    @staticmethod
    def objects(value):
        if isinstance(value, dict):
            yield value
            for key in ("@graph", "itemListElement", "mainEntity", "item", "offers", "hasVariant"):
                if isinstance(value.get(key), (dict, list)):
                    yield from Core.objects(value[key])
        elif isinstance(value, list):
            for item in value:
                yield from Core.objects(item)

    @staticmethod
    def url(value, base):
        from urllib.parse import urljoin

        return urljoin(base, value)

    @staticmethod
    def meta_values(_payload):
        return {}


class Worker:
    core = Core()
    FALLBACK_HTML_ROUTES = {"bay_smokes": ["https://bay-smokes.com/collections/thca-flower"]}
    PRODUCT_PATHS = ("/product/", "/products/")
    _runs = 0

    @staticmethod
    def path_text(target):
        return target.replace("-", " ")

    @staticmethod
    def has_product_evidence(value):
        normalized = str(value).casefold()
        return "thca" in normalized and "flower" in normalized and "pre-roll" not in normalized

    @staticmethod
    def product_detail_evidence(_payload, target):
        return target

    @staticmethod
    def card_candidates(_payload, _route):
        return []

    @staticmethod
    def run(*_args, **_kwargs):
        Worker._runs += 1
        return 0


def test_route_replacements_and_execution_boundary_repair():
    worker = Worker()
    state = route_repair.install(worker)
    assert state["repaired_sources"] == 1
    bay = next(source for source in worker.core.SOURCES if source[0] == "bay_smokes")
    assert all("bay-smokes.com" not in route[1] for route in bay[2])
    assert any(route[1].startswith("https://baysmokes.com/") for route in bay[2])

    worker.core.SOURCES = [
        (source_id, vendor, [*(routes or []), ("html", "https://bay-smokes.com/dead", "storewide")])
        if source_id == "bay_smokes" else (source_id, vendor, routes)
        for source_id, vendor, routes in worker.core.SOURCES
    ]
    assert worker.run() == 0
    bay = next(source for source in worker.core.SOURCES if source[0] == "bay_smokes")
    assert all("bay-smokes.com" not in route[1] for route in bay[2])


def test_first_party_jsonld_and_bigcommerce_price_enrichment():
    payload = """
    <script type="application/ld+json">
    {"@type":"Product","name":"Blue Dream THCA Flower","image":"/image.jpg",
     "offers":{"@type":"Offer","price":"49.95","availability":"https://schema.org/InStock"}}
    </script>
    <div data-product-price-without-tax-value="59.95">Add to cart</div>
    """
    values = route_repair.enrich_meta_values(Core, lambda _payload: {}, payload)
    assert values["product:price:amount"] == "49.95"
    assert values["product:availability"] == "in_stock"
    assert values["og:image"] == "/image.jpg"


def test_visible_product_detail_evidence_and_root_slug_discovery():
    worker = Worker()
    payload = """
    <html><body>
      <a href="/blue-dream-thca-flower/">Blue Dream THCA Flower</a>
      <a href="/collections/flower">THCA Flower Collection</a>
      <main>Premium loose Blue Dream THCA flower buds. Available in 3.5g and 7g.</main>
    </body></html>
    """
    evidence = route_repair.add_visible_product_evidence(worker, lambda _p, _t: "", payload, "")
    assert worker.has_product_evidence(evidence)
    candidates = route_repair.discover_evidenced_links(
        worker,
        lambda _payload, _route: [],
        payload,
        ("html", "https://example.test/thca-flower/", "thca_flower"),
    )
    assert [row["url"] for row in candidates] == ["https://example.test/blue-dream-thca-flower/"]
