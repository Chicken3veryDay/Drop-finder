from pathlib import Path

path = Path("web/src/features/marketplace/marketplace.css")
text = path.read_text(encoding="utf-8")
old = ".df-expanded-actions {\n  display: flex;\n"
new = '''.df-detail-state {
  display: grid;
  align-content: center;
  justify-items: start;
  gap: 0.65rem;
  min-height: 5rem;
  color: var(--df-muted);
}

.df-detail-state p {
  margin: 0;
}

.df-detail-state button {
  min-height: 2.25rem;
  border: 1px solid var(--df-border-strong);
  border-radius: 0.35rem;
  background: transparent;
  color: var(--df-text);
  padding: 0.45rem 0.65rem;
  cursor: pointer;
}

.df-detail-state button:hover {
  background: rgb(255 255 255 / 5%);
}

.df-expanded-actions {
  display: flex;
'''
if text.count(old) != 1:
    raise SystemExit(f"expanded-actions anchor count: {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
