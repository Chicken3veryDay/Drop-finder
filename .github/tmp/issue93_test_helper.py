from pathlib import Path

path = Path("web/test/catalog-cache-corruption.test.mjs")
text = path.read_text(encoding="utf-8")
old = '''function validGeneration(overrides = {}) {
  const generationId = overrides.generationId ?? 'generation-1';
  return {
'''
new = '''function validGeneration(overrides = {}) {
  const {
    manifest: manifestOverrides = {},
    index: indexOverrides = {},
    ...generationOverrides
  } = overrides;
  const generationId = generationOverrides.generationId ?? 'generation-1';
  return {
'''
if text.count(old) != 1:
    raise SystemExit(f"validGeneration header anchors: {text.count(old)}")
text = text.replace(old, new, 1)
text = text.replace("      ...(overrides.manifest ?? {}),\n", "      ...manifestOverrides,\n", 1)
text = text.replace("      ...(overrides.index ?? {}),\n", "      ...indexOverrides,\n", 1)
text = text.replace("    ...overrides,\n", "    ...generationOverrides,\n", 1)
path.write_text(text, encoding="utf-8")
