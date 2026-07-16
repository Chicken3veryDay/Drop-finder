from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one exact replacement, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def main() -> int:
    replace_exact(
        "scripts/catalog_v4/builder.py",
        '''            grams, source_weight_label = normalize_weight(
                raw.get("grams") if raw.get("grams") not in (None, "") else raw.get("weight_grams"),
                variant_label or raw.get("weight") or raw.get("size"),
            )''',
        '''            adapter_weight = raw.get("weight_grams")
            legacy_weight = raw.get("grams")
            weight_value = adapter_weight if adapter_weight not in (None, "") else legacy_weight
            weight_label = variant_label or raw.get("weight") or raw.get("size") or source_title
            grams, source_weight_label = normalize_weight(
                weight_value,
                weight_label,
                require_explicit_label=(
                    adapter_weight in (None, "") and legacy_weight not in (None, "")
                ),
            )''',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
