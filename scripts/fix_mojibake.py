"""Perbaiki teks mojibake (UTF-8 yang terbaca latin-1) di frontend."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

MAPPINGS = [
    ("â€¦", "…"),
    ("â€”", "—"),
    ("â€“", "–"),
    ("â€¢", "•"),
    ("â–¶", "▶"),
    ("â‰ˆ", "≈"),
    ("â†»", "↻"),
    ("Ã—", "×"),
    ("Â·", "·"),
    ("Belum dinilai", "Not scored yet"),
    ("Menghitung…", "Calculating…"),
]

changed = {}
for path in list(SRC.rglob("*.tsx")) + list(SRC.rglob("*.ts")):
    text = path.read_text(encoding="utf-8")
    original = text
    hits = 0
    for old, new in MAPPINGS:
        if old in text:
            hits += text.count(old)
            text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        changed[str(path.relative_to(ROOT))] = hits

for name, count in sorted(changed.items()):
    print(f"{name}: {count} teks diperbaiki")
print("file berubah:", len(changed))
