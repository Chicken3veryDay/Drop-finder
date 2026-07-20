from pathlib import Path

source = Path("web/src/features/integration/register-marketplace-props.tsx")
text = source.read_text(encoding="utf-8")
old = '''      tabIndex={-1}
      aria-label="Marketplace results viewport"
'''
new = '''      tabIndex={-1}
'''
if text.count(old) != 1:
    raise SystemExit(f"viewport accessibility anchor count: {text.count(old)}")
source.write_text(text.replace(old, new, 1), encoding="utf-8")

test = Path("web/src/features/integration/marketplace-virtualization.test.tsx")
text = test.read_text(encoding="utf-8")
old = '    const viewport = view.getByLabelText("Marketplace results viewport") as HTMLDivElement;\n'
new = '    const viewport = view.container.querySelector(".df-virtual-viewport") as HTMLDivElement;\n'
if text.count(old) != 2:
    raise SystemExit(f"viewport test anchor count: {text.count(old)}")
test.write_text(text.replace(old, new), encoding="utf-8")
