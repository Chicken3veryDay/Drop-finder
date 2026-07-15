"""CLI for deterministic profile verification, discovery parsing, and catalog annotation."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .annotate import annotate_products
from .coverage import verify_coverage
from .models import DocumentCandidate, ParsedLabRecord, Provenance
from .live_check import run_live_checks
from .parsers import parse_document


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate(value: dict[str, Any]) -> DocumentCandidate:
    provenance = value.get("provenance")
    return DocumentCandidate(**{**value, "provenance": Provenance(**provenance) if isinstance(provenance, dict) else None})


def _parsed(value: dict[str, Any]) -> ParsedLabRecord:
    value = dict(value)
    value["limitations"] = tuple(value.get("limitations") or ())
    return ParsedLabRecord(**value)


def command_verify(args: argparse.Namespace) -> int:
    result = verify_coverage(args.profiles, args.sources, args.research)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def command_parse(args: argparse.Namespace) -> int:
    candidate = _candidate(_read_json(args.candidate))
    payload = args.document.read_bytes()
    result = parse_document(payload, args.content_type, candidate)
    args.output.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def command_annotate(args: argparse.Namespace) -> int:
    products_payload = _read_json(args.products)
    products = products_payload.get("products", products_payload) if isinstance(products_payload, dict) else products_payload
    candidates = [_candidate(item) for item in _read_json(args.candidates)]
    records = [_parsed(item) for item in _read_json(args.records)]
    profiles_payload = _read_json(args.profiles)
    profiles = {item["vendor_id"]: item for item in profiles_payload["vendors"]}
    annotated = annotate_products(products, candidates, records, profiles)
    args.output.write_text(json.dumps({"product_count": len(annotated), "products": annotated}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def command_live_check(args: argparse.Namespace) -> int:
    result = run_live_checks(args.profiles, workers=args.workers, timeout=args.timeout, max_bytes=args.max_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("probe_count", "success_count", "failure_count")}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.vendor_adapters.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="verify SOURCES/profile/report coverage")
    verify.add_argument("--profiles", type=Path, default=Path("data/vendor_profiles.json"))
    verify.add_argument("--sources", type=Path, default=Path("scripts/cloud_scan.py"))
    verify.add_argument("--research", type=Path, default=Path("research/vendors"))
    verify.set_defaults(func=command_verify)
    parse = sub.add_parser("parse", help="parse one bounded public document fixture")
    parse.add_argument("--candidate", type=Path, required=True)
    parse.add_argument("--document", type=Path, required=True)
    parse.add_argument("--content-type", default="application/octet-stream")
    parse.add_argument("--output", type=Path, required=True)
    parse.set_defaults(func=command_parse)
    annotate = sub.add_parser("annotate", help="annotate a catalog without dropping products")
    annotate.add_argument("--products", type=Path, required=True)
    annotate.add_argument("--candidates", type=Path, required=True)
    annotate.add_argument("--records", type=Path, required=True)
    annotate.add_argument("--profiles", type=Path, default=Path("data/vendor_profiles.json"))
    annotate.add_argument("--output", type=Path, required=True)
    annotate.set_defaults(func=command_annotate)
    live = sub.add_parser("live-check", help="run bounded GET-only public maintenance probes")
    live.add_argument("--profiles", type=Path, default=Path("data/vendor_profiles.json"))
    live.add_argument("--workers", type=int, default=4)
    live.add_argument("--timeout", type=float, default=8.0)
    live.add_argument("--max-bytes", type=int, default=512000)
    live.add_argument("--output", type=Path, default=Path("artifacts/vendor-live-check.json"))
    live.set_defaults(func=command_live_check)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
