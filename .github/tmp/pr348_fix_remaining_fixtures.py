from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/test/catalog-bounds.test.mjs",
    "  await cache.putComplete({ generationId: 'cached', manifest: {}, index: { products: [] }, activatedAt: 1, source: 'cache' });\n",
    "  const cachedAt = Date.now();\n"
    "  await cache.putComplete({\n"
    "    generationId: 'cached',\n"
    "    manifest: { generated_at: new Date(cachedAt).toISOString() },\n"
    "    index: { products: [] },\n"
    "    activatedAt: cachedAt,\n"
    "    source: 'cache',\n"
    "  });\n",
)
replace_once(
    "web/test/catalog-generation-freshness.test.mjs",
    "    generation_id: generationId,\n    index: {\n",
    "    generation_id: generationId,\n    generated_at: new Date().toISOString(),\n    index: {\n",
)
