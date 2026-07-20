from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/features/integration/register-marketplace-props.tsx",
    '''      tabIndex={-1}
      aria-label="Marketplace results viewport"
''',
    '''      tabIndex={-1}
      role="list"
      aria-label={`${total} marketplace results`}
''',
)

replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '''        <div className="df-list" role="list" aria-label={`${query.total} marketplace results`}>
''',
    '''        <div
          className="df-list"
          role={virtualization ? undefined : "list"}
          aria-label={virtualization ? undefined : `${query.total} marketplace results`}
        >
''',
)

test = Path("web/src/features/integration/marketplace-virtualization.test.tsx")
text = test.read_text(encoding="utf-8")
old = '    const viewport = view.getByLabelText("Marketplace results viewport") as HTMLDivElement;\n'
new = '    const viewport = view.getByRole("list", { name: "2 marketplace results" }) as HTMLDivElement;\n'
if text.count(old) != 2:
    raise SystemExit(f"viewport test anchor count: {text.count(old)}")
test.write_text(text.replace(old, new), encoding="utf-8")
