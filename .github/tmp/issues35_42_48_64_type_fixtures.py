from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/features/integration/document-overlay-controls.test.tsx",
    '} as typeof state;\n',
    '} as unknown as typeof state;\n',
)
replace_once(
    "web/src/features/integration/document-cache.integration.test.ts",
    "    scale: 1,\n    fitWidth: true,\n",
    "    scale: 1,\n    renderedScale: 1,\n    fitWidth: true,\n",
)
replace_once(
    "web/src/features/integration/document-cache.integration.test.ts",
    "    zoomOut: vi.fn(),\n    setFitWidth: vi.fn(),\n",
    "    zoomOut: vi.fn(),\n    resetZoom: vi.fn(),\n    setFitWidth: vi.fn(),\n",
)
