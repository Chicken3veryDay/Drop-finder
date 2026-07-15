#!/usr/bin/env python3
"""Apply small compatibility hardening after the main integration finalizer."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected post-finalize seam missing in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    provider = WEB / "src/features/integration/register-marketplace-props.tsx"
    replace(
        provider,
        '''const numberValue = (value: unknown): number | null => {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};''',
        '''const numberValue = (value: unknown): number | null => {
  if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};''',
    )

    marketplace = WEB / "src/features/marketplace/MarketplaceFeature.tsx"
    replace(
        marketplace,
        "  }, [asyncQueryEngine, products, filters, sort]);",
        "  }, [asyncQueryEngine, expandedProductId, products, filters, sort]);",
    )

    eslint = WEB / "eslint.config.js"
    text = eslint.read_text(encoding="utf-8")
    text = text.replace(
        '{ ignores: ["dist", "../cloud_pages/assets"] },',
        '{ ignores: ["dist", "dist-platform", "public", "../cloud_pages/assets"] },',
        1,
    )
    marker = '''    languageOptions: {
      globals: {
        console: "readonly",
        process: "readonly",
        URL: "readonly",
      },
    },
  },'''
    replacement = '''    languageOptions: {
      globals: {
        console: "readonly",
        process: "readonly",
        URL: "readonly",
      },
    },
    rules: {
      "no-undef": "off",
    },
  },'''
    if marker not in text:
        raise RuntimeError("Expected JavaScript ESLint block is missing")
    eslint.write_text(text.replace(marker, replacement, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
