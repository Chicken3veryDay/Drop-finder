"""DropFinder vendor compliance and public laboratory evidence adapters."""
from .annotate import annotate_products
from .coverage import verify_coverage
from .discovery import discover_html_documents, discover_json_documents
from .fetch import FetchResult, fetch_public_document
from .mapping import map_documents, score_candidate
from .models import DocumentCandidate, MappingDecision, ParsedLabRecord, Provenance, stable_document_id
from .parsers import parse_document, parse_lab_text, parse_pdf, parse_structured_html, parse_structured_json
from .registry import VendorAdapter, VendorRegistry

__all__ = [
    "DocumentCandidate", "FetchResult", "MappingDecision", "ParsedLabRecord", "Provenance",
    "VendorAdapter", "VendorRegistry", "annotate_products", "discover_html_documents",
    "discover_json_documents", "fetch_public_document", "map_documents", "parse_document",
    "parse_lab_text", "parse_pdf", "parse_structured_html", "parse_structured_json",
    "score_candidate", "stable_document_id", "verify_coverage",
]
