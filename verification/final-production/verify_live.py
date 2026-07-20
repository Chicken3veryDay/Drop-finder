from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import mimetypes
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def strict_loads(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant {value}")))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AssetParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        candidate = values.get("src") if tag in {"script", "img"} else values.get("href") if tag == "link" else None
        if candidate:
            parsed = urllib.parse.urlparse(candidate)
            if not parsed.scheme and not parsed.netloc:
                self.assets.add(parsed.path.lstrip("./"))


def local_json(root: Path, path: str) -> Any:
    return strict_loads((root / path).read_bytes())


def fetch(base_url: str, path: str) -> tuple[bytes, dict[str, str], int, str]:
    target = urllib.parse.urljoin(base_url.rstrip("/") + "/", path)
    separator = "&" if "?" in target else "?"
    request = urllib.request.Request(
        f"{target}{separator}closure_verify={time.time_ns()}",
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache", "User-Agent": "DropFinder-final-closure/1"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read()
        return body, {key.lower(): value for key, value in response.headers.items()}, response.status, response.geturl()


def expected_content_type(path: str) -> tuple[str, ...]:
    if path in {"", "index.html"} or path.endswith(".html"):
        return ("text/html",)
    if path.endswith((".json", ".webmanifest")):
        return ("application/json", "application/manifest+json", "text/json", "text/plain")
    if path.endswith(".js"):
        return ("javascript", "text/plain")
    if path.endswith(".css"):
        return ("text/css", "text/plain")
    if path.endswith(".svg"):
        return ("image/svg+xml", "text/plain")
    guessed = mimetypes.guess_type(path)[0]
    return (guessed,) if guessed else tuple()


def add_reference(paths: set[str], value: Any) -> None:
    if isinstance(value, str) and value and not urllib.parse.urlparse(value).scheme:
        paths.add(value.lstrip("./"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--local-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.local_root
    receipt = strict_loads(args.receipt.read_bytes())
    expected_generation = str(receipt["generation_id"])
    expected_publication = str(receipt["publication_commit"])

    required = {
        "",
        "index.html",
        "manifest.webmanifest",
        "app-shell.json",
        "sw.js",
        "data/catalog.json",
        "data/status.json",
        "data/runtime.json",
        "data/catalog-v4/manifest.json",
    }
    paths = set(required)

    shell = local_json(root, "app-shell.json")
    if shell.get("schema_version") != "dropfinder-app-shell-v1":
        raise SystemExit("unexpected app-shell schema")
    for asset in shell.get("assets", []):
        add_reference(paths, asset)
    for record in shell.get("records", []):
        add_reference(paths, record.get("path"))

    catalog_manifest = local_json(root, "data/catalog-v4/manifest.json")
    if catalog_manifest.get("generation_id") != expected_generation:
        raise SystemExit("receipt/catalog-v4 generation mismatch")
    for key in ("compact_index", "vendor_profiles", "rejections"):
        entry = catalog_manifest.get(key)
        if isinstance(entry, dict):
            add_reference(paths, entry.get("path"))
    for entry in catalog_manifest.get("product_detail_shards", []):
        if isinstance(entry, dict):
            add_reference(paths, entry.get("path"))

    index_html = (root / "index.html").read_text(encoding="utf-8")
    html_assets = AssetParser()
    html_assets.feed(index_html)
    paths.update(html_assets.assets)

    vite_candidates = [root / ".vite" / "manifest.json", root / "vite-manifest.json"]
    vite_path = next((candidate for candidate in vite_candidates if candidate.exists()), None)
    if vite_path:
        vite = strict_loads(vite_path.read_bytes())
        paths.add(vite_path.relative_to(root).as_posix())
        for entry in vite.values() if isinstance(vite, dict) else []:
            if not isinstance(entry, dict):
                continue
            add_reference(paths, entry.get("file"))
            for key in ("css", "assets"):
                for asset in entry.get(key, []) if isinstance(entry.get(key), list) else []:
                    add_reference(paths, asset)

    results: dict[str, Any] = {}
    public_json: dict[str, Any] = {}
    for path in sorted(paths):
        local_path = root / (path or "index.html")
        if not local_path.is_file():
            raise SystemExit(f"referenced local path missing: {path or '/'}")
        local_bytes = local_path.read_bytes()
        public_bytes, headers, status, final_url = fetch(args.base_url, path)
        if status != 200:
            raise SystemExit(f"HTTP {status} for {path or '/'}")
        if public_bytes != local_bytes:
            raise SystemExit(f"public bytes differ from publication commit for {path or '/'}")
        content_type = headers.get("content-type", "").lower()
        expected_types = expected_content_type(path or "index.html")
        if expected_types and not any(value and value in content_type for value in expected_types):
            raise SystemExit(f"unexpected content type for {path or '/'}: {content_type}")
        parsed_schema = None
        if path.endswith((".json", ".webmanifest")):
            parsed = strict_loads(public_bytes)
            public_json[path] = parsed
            if isinstance(parsed, dict):
                parsed_schema = parsed.get("schema_version") or parsed.get("catalog_schema_version")
        results[path or "/"] = {
            "status": status,
            "final_url": final_url,
            "content_type": content_type,
            "content_length": len(public_bytes),
            "sha256": sha256(public_bytes),
            "schema": parsed_schema,
            "cache_control": headers.get("cache-control"),
            "etag": headers.get("etag"),
            "last_modified": headers.get("last-modified"),
        }

    generation_sources = {
        "catalog": public_json["data/catalog.json"].get("generation_id"),
        "status": public_json["data/status.json"].get("generation_id"),
        "runtime": public_json["data/runtime.json"].get("generation_id"),
        "manifest": public_json["data/catalog-v4/manifest.json"].get("generation_id"),
    }
    compact_path = catalog_manifest["compact_index"]["path"]
    generation_sources["compact_index"] = public_json[compact_path].get("generation_id")
    for name, generation in generation_sources.items():
        if str(generation) != expected_generation:
            raise SystemExit(f"generation mismatch for {name}: {generation}")

    referenced_hashes: dict[str, str] = {}
    for entry in [catalog_manifest.get("compact_index"), catalog_manifest.get("vendor_profiles"), catalog_manifest.get("rejections")]:
        if isinstance(entry, dict):
            referenced_hashes[str(entry["path"])] = str(entry["sha256"])
    for entry in catalog_manifest.get("product_detail_shards", []):
        referenced_hashes[str(entry["path"])] = str(entry["sha256"])
    for path, expected_hash in referenced_hashes.items():
        actual_hash = results[path]["sha256"]
        if actual_hash != expected_hash:
            raise SystemExit(f"manifest hash mismatch for {path}: {actual_hash} != {expected_hash}")

    for record in shell.get("records", []):
        path = str(record["path"]).lstrip("./")
        if results[path]["sha256"] != record["sha256"] or results[path]["content_length"] != record["bytes"]:
            raise SystemExit(f"app-shell record mismatch for {path}")

    sw_text = (root / "sw.js").read_text(encoding="utf-8")
    for required_sw_token in ("deploymentNamespace", "GENERATION_CACHE_PREFIX", "SHELL_MANIFEST", "networkFirst"):
        if required_sw_token not in sw_text:
            raise SystemExit(f"service worker missing {required_sw_token}")

    report = {
        "verified": True,
        "public_url": args.base_url,
        "publication_commit": expected_publication,
        "generation_id": expected_generation,
        "product_count": catalog_manifest.get("product_count"),
        "variant_count": catalog_manifest.get("in_stock_variant_count"),
        "endpoint_count": len(results),
        "generations": generation_sources,
        "endpoints": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("verified", "generation_id", "product_count", "variant_count", "endpoint_count")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
