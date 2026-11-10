"""
Normalisasi metadata YouTube sebelum dikirim ke Data API v3.

YouTube sangat ketat: judul/deskripsi dengan karakter `<`/`>` atau karakter
kontrol ditolak (`invalidTitle` / `invalidDescription`), dan total panjang tag
dibatasi 500 karakter walau jumlahnya ≤ 15. Tanpa normalisasi, unggahan gagal
dengan HTTP 400 yang membingungkan.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

MAX_TITLE = 100
MAX_DESCRIPTION = 5000
MAX_TAGS = 15
MAX_TAG_LENGTH = 60
MAX_TAGS_TOTAL = 450  # 50 karakter di bawah batas keras YouTube (500)

ALLOWED_PRIVACY = {"public", "unlisted", "private"}
ALLOWED_CATEGORIES = {
    "1", "2", "10", "15", "17", "19", "20", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40",
    "41", "42", "43", "44",
}
DEFAULT_CATEGORY = "22"  # People & Blogs

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_ISH = re.compile(r"[<>]")
_SPACES = re.compile(r"[ \t\u00a0]+")


def _strip_unsafe(value: Any, *, keep_newlines: bool) -> str:
    """Buang karakter kontrol + `<`/`>`, rapikan spasi (newline opsional)."""
    text = _CONTROL.sub(" ", str(value or ""))
    # YouTube menolak `<`/`>`; ganti dengan spasi supaya kata tidak menempel.
    text = _HTML_ISH.sub(" ", text)
    if keep_newlines:
        text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.splitlines())
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    return _SPACES.sub(" ", text).strip()


def sanitize_title(title: Any, fallback: str = "Shorts") -> str:
    clean = _strip_unsafe(title, keep_newlines=False)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        clean = fallback
    return clean[:MAX_TITLE].rstrip()


def sanitize_description(description: Any) -> str:
    clean = _strip_unsafe(description, keep_newlines=True)
    return clean[:MAX_DESCRIPTION].rstrip()


def sanitize_tags(tags: Iterable[Any]) -> List[str]:
    """Rapikan tag: unik, tanpa spasi ganda, total ≤ 450 karakter."""
    result: List[str] = []
    seen: set[str] = set()
    total = 0
    for raw in tags or []:
        tag = _strip_unsafe(raw, keep_newlines=False).strip(",;")
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            tag = tag[:MAX_TAG_LENGTH].rstrip()
            key = tag.lower()
        if len(result) >= MAX_TAGS or total + len(tag) > MAX_TAGS_TOTAL:
            break
        seen.add(key)
        result.append(tag)
        total += len(tag)
    return result


def normalize_privacy(value: Any) -> str:
    privacy = str(value or "").strip().lower()
    return privacy if privacy in ALLOWED_PRIVACY else "unlisted"


def normalize_category(value: Any, fallback: str = DEFAULT_CATEGORY) -> str:
    category = str(value or "").strip()
    if category in ALLOWED_CATEGORIES:
        return category
    return fallback if fallback in ALLOWED_CATEGORIES else DEFAULT_CATEGORY


def build_snippet(
    *,
    title: Any,
    description: Any,
    tags: Iterable[Any],
    category_id: Any = DEFAULT_CATEGORY,
) -> Dict[str, Any]:
    """Payload `snippet` siap kirim + nilai yang dipakai untuk logging."""
    return {
        "title": sanitize_title(title),
        "description": sanitize_description(description),
        "tags": sanitize_tags(tags),
        "categoryId": normalize_category(category_id),
    }
