from pathlib import Path

path = Path("scripts/autonomous_worker_v2.py")
text = path.read_text(encoding="utf-8")

old = '''        nearby = worker.core.text(payload[match.start() : min(len(payload), match.end() + 2200)])
        prices = [worker.core.num(value) for value in worker.PRICE.findall(nearby)]
        price = next((value for value in prices if value is not None), None)
        stock = (
            "out_of_stock"
            if "out of stock" in nearby.lower()
            else "in_stock"
            if any(token in nearby.lower() for token in ("add to cart", "choose an option", "in stock"))
            else ""
        )
        candidate = {
            "name": label,
            "url": target,
            "price": price,
            "stock": stock,
            "card_evidence": form_text,
            "candidate_score": _candidate_score(label, target, price),
        }
'''
new = '''        # Anchor discovery does not establish ownership of surrounding price or
        # availability text. Those fields are admitted only from this URL's own
        # fetched product-detail metadata below.
        candidate = {
            "name": label,
            "url": target,
            "price": None,
            "stock": "",
            "card_evidence": form_text,
            "candidate_score": _candidate_score(label, target, None),
        }
'''
if text.count(old) != 1:
    raise SystemExit(f"card proximity anchor count: {text.count(old)}")
text = text.replace(old, new, 1)

old = '''    price = (
        meta.get("product:price:amount")
        or meta.get("og:price:amount")
        or candidate.get("price")
    )
    stock = meta.get("product:availability") or candidate.get("stock")
'''
new = '''    price = meta.get("product:price:amount") or meta.get("og:price:amount")
    stock = meta.get("product:availability")
'''
if text.count(old) != 1:
    raise SystemExit(f"detail fallback anchor count: {text.count(old)}")
text = text.replace(old, new, 1)

old = '''    assert rows[0]["name"] == "Blue Dream THCA Flower"
    assert rows[0]["price"] == 24.99
'''
new = '''    assert rows[0]["name"] == "Blue Dream THCA Flower"
    assert rows[0]["price"] is None
    assert rows[0]["stock"] == ""
'''
if text.count(old) != 1:
    raise SystemExit(f"self-test card ownership anchor count: {text.count(old)}")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
