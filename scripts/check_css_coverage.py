"""Cek apakah semua class yang dipakai komponen ada di theme.css / landing.css."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

css = (
    (ROOT / "frontend/src/app/theme.css").read_text(encoding="utf-8")
    + (ROOT / "frontend/src/app/landing.css").read_text(encoding="utf-8")
)

tokens: set[str] = set()
for path in SRC.rglob("*.tsx"):
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r'className="([^"]+)"', text):
        for token in match.group(1).split():
            tokens.add(token)
    # kelas dinamis di template literal: className={`x ${cond ? "y" : ""}`}
    for match in re.finditer(r"className=\{`([^`]+)`\}", text):
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]*", match.group(1)):
            tokens.add(token)

TAILWIND = {
    "flex", "items-center", "gap-3", "px-4", "py-2", "rounded-lg", "border",
    "center", "text-xs", "font-bold", "text-gray-400", "text-yellow-400",
    "bg-white/10", "border-white/20", "animate-spin",
}
INTERPOLATION = {"selected", "band", "active", "open", "danger", "true", "false"}

missing = sorted(
    token
    for token in tokens
    if token not in TAILWIND
    and token not in INTERPOLATION
    and f".{token}" not in css
)
print(f"total class terpakai: {len(tokens)}")
print(f"tanpa style ({len(missing)}):")
for token in missing:
    print("  -", token)
