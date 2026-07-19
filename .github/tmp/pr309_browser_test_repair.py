from pathlib import Path

path = Path("web/src/features/marketplace/MarketplaceFeature.query-path.test.tsx")
text = path.read_text(encoding="utf-8")
start_marker = '  it("does not restart page zero when only detail-enrichment fields change", async () => {'
end_marker = '  it("retains the synchronous query fallback when no async engine is available", () => {'
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("detail enrichment test boundary not found")
block = text[start:end]
if "const asyncEngine: MarketplaceAsyncQueryCapability" not in block:
    anchor = "    }));\n    const view = render(\n"
    if block.count(anchor) != 1:
        raise SystemExit(f"stable engine insertion: expected one anchor, found {block.count(anchor)}")
    block = block.replace(
        anchor,
        "    }));\n    const asyncEngine: MarketplaceAsyncQueryCapability = { query: asynchronousQuery };\n    const view = render(\n",
        1,
    )
old = '        asyncQueryEngine={{ query: asynchronousQuery }}\n'
if block.count("asyncQueryEngine={asyncEngine}") != 2:
    if block.count(old) != 2:
        raise SystemExit(f"stable engine props: expected two inline wrappers, found {block.count(old)}")
    block = block.replace(old, "        asyncQueryEngine={asyncEngine}\n")
path.write_text(text[:start] + block + text[end:], encoding="utf-8")
