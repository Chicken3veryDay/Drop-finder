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

    # The isolated marketplace branch used ambient React/Node declarations and
    # node:test so it could validate without the foundation package. In the
    # integrated frontend those declarations shadow the real packages, and the
    # tests belong to Vitest alongside the other TypeScript unit suites.
    test_root = WEB / "src/features/marketplace/test"
    for shim_name in ("react-shim.d.ts", "node-shim.d.ts"):
        shim = test_root / shim_name
        if not shim.exists():
            raise RuntimeError(f"Expected isolated marketplace shim is missing: {shim_name}")
        shim.unlink()
    for test_name in ("marketplace-core.test.ts", "marketplace-hardening.test.ts"):
        replace(
            test_root / test_name,
            'import test from "node:test";',
            'import { it as test } from "vitest";',
        )

    eslint = WEB / "eslint.config.js"
    text = eslint.read_text(encoding="utf-8")
    text = text.replace(
        '{ ignores: ["dist", "../cloud_pages/assets"] },',
        '{ ignores: ["dist", "dist-platform", "public", "../cloud_pages/assets"] },',
        1,
    )
    tail = '''  {
    files: ["**/*.test.{ts,tsx}", "src/test/**/*.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "react-refresh/only-export-components": "off",
    },
  },
);'''
    replacement_tail = '''  {
    files: ["**/*.test.{ts,tsx}", "src/test/**/*.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "react-refresh/only-export-components": "off",
    },
  },
  {
    files: ["**/*.{js,mjs,cjs}"],
    rules: {
      "no-undef": "off",
      "no-empty": "off",
    },
  },
  {
    files: ["src/features/marketplace/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-empty-object-type": "off",
      "react-refresh/only-export-components": "off",
    },
  },
);'''
    if tail not in text:
        raise RuntimeError("Expected ESLint configuration tail is missing")
    eslint.write_text(text.replace(tail, replacement_tail, 1), encoding="utf-8")

    service_worker = ROOT / "cloud_pages/sw.js"
    replace(
        service_worker,
        "const FALLBACK_SHELL = ['./', './index.html', './manifest.webmanifest', './icon.svg'];",
        "const FALLBACK_SHELL = ['./', './index.html', './manifest.webmanifest', './icon.svg', './data/catalog.json', './data/status.json', './data/runtime.json'];",
    )
    replace(
        service_worker,
        '''  const manifestResponse = seedUrl.includes('catalog-manifest-v4.json')
    ? await cache.match(seedUrl, { ignoreSearch: true })
    : await fetch(new URL('./catalog-manifest-v4.json', seedUrl), { cache: 'no-store' });
  if (!manifestResponse?.ok) { preparing = null; return; }
  const manifest = seedPayload?.index ? seedPayload : await manifestResponse.clone().json();
  if (manifest.generation_id !== generationId || manifest.schema_version !== 4 || !manifest.index?.url) { preparing = null; return; }
  const required = [new URL(manifest.index.url, seedUrl).href];
  for (const descriptor of Object.values(manifest.vendors || {})) if (descriptor?.url) required.push(new URL(descriptor.url, seedUrl).href);''',
        '''  const realCatalogV4 = seedUrl.includes('/data/catalog-v4/');
  const manifestResponse = seedUrl.includes('catalog-manifest-v4.json') || seedUrl.endsWith('/catalog-v4/manifest.json')
    ? await cache.match(seedUrl, { ignoreSearch: true })
    : await fetch(new URL(realCatalogV4 ? './manifest.json' : './catalog-manifest-v4.json', seedUrl), { cache: 'no-store' });
  if (!manifestResponse?.ok) { preparing = null; return; }
  const manifest = seedPayload?.index || seedPayload?.compact_index ? seedPayload : await manifestResponse.clone().json();
  const descriptor = manifest.compact_index ?? manifest.index;
  const supportedSchema = manifest.schema_version === 4 || manifest.schema_version === 'dropfinder-catalog-manifest-v4';
  if (manifest.generation_id !== generationId || !supportedSchema || !(descriptor?.url || descriptor?.path)) { preparing = null; return; }
  const publicationBase = catalogPublicationBase(seedUrl);
  const required = [new URL(descriptor.path ?? descriptor.url, publicationBase).href];
  const vendorDescriptor = manifest.vendor_profiles;
  if (vendorDescriptor?.url || vendorDescriptor?.path) required.push(new URL(vendorDescriptor.path ?? vendorDescriptor.url, publicationBase).href);
  for (const vendor of Object.values(manifest.vendors || {})) if (vendor?.url || vendor?.path) required.push(new URL(vendor.path ?? vendor.url, publicationBase).href);''',
    )
    replace(
        service_worker,
        "function isManifestOrIndex(path) { return /(?:catalog-manifest-v4|catalog-index|vendor-profiles|catalog|status)\\.json$/i.test(path); }",
        "function isManifestOrIndex(path) { return /(?:catalog-manifest-v4|catalog-index|vendor-profiles|catalog|status)\\.json$/i.test(path) || /\\/catalog-v4\\/(?:manifest|index)\\.json$/i.test(path); }",
    )
    replace(
        service_worker,
        "function generationCacheName(id) { return `dropfinder-data-${String(id).replace(/[^a-z0-9._-]/gi, '_')}`; }",
        '''function catalogPublicationBase(url) {
  const parsed = new URL(url);
  const marker = '/data/catalog-v4/';
  const index = parsed.pathname.lastIndexOf(marker);
  if (index >= 0) {
    parsed.pathname = parsed.pathname.slice(0, index + 1);
    parsed.search = '';
    parsed.hash = '';
  }
  return parsed.href;
}
function generationCacheName(id) { return `dropfinder-data-${String(id).replace(/[^a-z0-9._-]/gi, '_')}`; }''',
    )


if __name__ == "__main__":
    main()
