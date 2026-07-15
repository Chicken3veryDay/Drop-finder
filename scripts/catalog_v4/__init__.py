"""DropFinder catalog v4 shopper-data generation.

The package consumes already-admitted strict-flower records and publishes a
stock-safe, grouped, provenance-aware static catalog for the marketplace.
"""

SCHEMA_VERSION = "dropfinder-catalog-v4"
MANIFEST_SCHEMA_VERSION = "dropfinder-catalog-manifest-v4"
INDEX_SCHEMA_VERSION = "dropfinder-marketplace-index-v4"
DETAIL_SCHEMA_VERSION = "dropfinder-product-details-v4"
VENDOR_SCHEMA_VERSION = "dropfinder-vendor-profiles-v1"
REJECTION_SCHEMA_VERSION = "dropfinder-catalog-rejections-v4"

from .builder import BuildResult, CatalogBuilder, build_catalog, write_result
from .selection import select_active_variant
from .verify import VerificationError, verify_publication

__all__ = [
    "BuildResult",
    "CatalogBuilder",
    "VerificationError",
    "build_catalog",
    "select_active_variant",
    "verify_publication",
    "write_result",
]
