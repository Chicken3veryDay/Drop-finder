from pathlib import Path

path = Path("scripts/multi_product/publication.py")
text = path.read_text(encoding="utf-8")
old = '''        evidence={"explicit_cannabis": True, "explicit_vape": True},
        volume_ml=1, price_per_ml=20,
'''
new = '''        evidence={"explicit_cannabis": True, "explicit_vape": True},
        volume_ml=1,
        quantity_value=1,
        quantity_unit="ml",
        comparison_metric="price_per_ml",
        comparison_price=20,
        price_per_ml=20,
'''
if new not in text:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"self-test vape fixture: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
