from pathlib import Path

path = Path("scripts/catalog_v4/builder.py")
text = path.read_text(encoding="utf-8")
old = '''                merged = dict(parent)
                merged.update(variant)
                merged.setdefault("source_title", raw.get("source_title") or raw.get("name") or raw.get("title"))
'''
new = '''                parent_documents = parent.get("documents") if isinstance(parent.get("documents"), list) else []
                child_documents = variant.get("documents") if isinstance(variant.get("documents"), list) else []
                merged = dict(parent)
                merged.update(variant)
                if parent_documents or "documents" in variant:
                    merged["documents"] = [*parent_documents, *child_documents]
                merged.setdefault("source_title", raw.get("source_title") or raw.get("name") or raw.get("title"))
'''
if text.count(old) != 1:
    raise SystemExit(f"flatten anchor count: {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
