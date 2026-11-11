"""
Builder subtitle ASS (Advanced SubStation Alpha) untuk klip vertikal.

Kenapa ASS, bukan SRT+force_style:
  * SRT memaksa satu blok teks panjang yang menutupi wajah,
  * ASS bisa mengatur jumlah kata per baris, posisi aman di atas UI YouTube,
    ukuran font proporsional terhadap tinggi video, dan **highlight per kata**
    (gaya CapCut/TikTok) tanpa merender ulang video.

Semua preset di `processor.CAPTION_STYLES` tetap dipakai: nilai `force_style`
di-parse lalu diskalakan dari basis PlayResY=288 ke tinggi video sebenarnya,
jadi tampilan konsisten di 9:16, 1:1, maupun 16:9.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.services.speech_boundaries import Word, extract_words

# Warna highlight kata aktif (gold) dalam format ASS &HBBGGRR.
DEFAULT_HIGHLIGHT = "&H006BC7F4"
LINE_BREAK = r"\N"


def _parse_force_style(force_style: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for part in (force_style or "").split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _scaled(value: str, height: int, default: float) -> int:
    """Skala nilai force_style dari basis 288 px ke tinggi video nyata."""
    try:
        base = float(value)
    except (TypeError, ValueError):
        base = default
    return max(1, int(round(base * height / 288.0)))


def group_into_cues(
    words: Sequence[Word],
    max_words: int = 5,
    max_chars: int = 26,
) -> List[List[Word]]:
    """Kelompokkan kata menjadi cue pendek (maks 5 kata / 26 karakter)."""
    cues: List[List[Word]] = []
    current: List[Word] = []
    for word in words:
        if current:
            text_len = sum(len(w.text) + 1 for w in current) + len(word.text)
            gap = word.start - current[-1].end
            if len(current) >= max_words or text_len > max_chars or gap > 0.65:
                cues.append(current)
                current = []
        current.append(word)
    if current:
        cues.append(current)
    return cues


def _ass_to_rgb(colour: str) -> tuple[int, int, int]:
    """ASS &HBBGGRR -> (r, g, b)."""
    value = (colour or "").replace("&H", "").replace("&", "")
    value = value[-6:].rjust(6, "0")
    return int(value[4:6], 16), int(value[2:4], 16), int(value[0:2], 16)


def pick_highlight(primary: str) -> str:
    """Warna kata aktif: putih bila teks sudah kekuningan, selain itu emas."""
    red, green, blue = _ass_to_rgb(primary)
    if red > 190 and green > 140 and blue < 150:
        return "&H00FFFFFF"
    return DEFAULT_HIGHLIGHT


def _cue_text(
    cue: Sequence[Word],
    active: Optional[int] = None,
    highlight: str = DEFAULT_HIGHLIGHT,
) -> str:
    """Teks cue dengan highlight pada kata aktif + maksimal 2 baris."""
    tokens = [w.text for w in cue]
    if len(tokens) > 2 and len(" ".join(tokens)) > 14:
        split = max(1, len(tokens) // 2)
        lines = [tokens[:split], tokens[split:]]
    else:
        lines = [tokens]

    rendered: List[str] = []
    index = 0
    for line in lines:
        parts: List[str] = []
        for token in line:
            if active is not None and index == active:
                parts.append(f"{{\\c{highlight}\\b1}}{token}{{\\r}}")
            else:
                parts.append(token)
            index += 1
        rendered.append(" ".join(parts))
    return LINE_BREAK.join(rendered)


def build_ass(
    segments: Sequence[Dict[str, Any]],
    output_path: str,
    force_style: str,
    width: int,
    height: int,
    clip_start: float = 0.0,
    clip_end: Optional[float] = None,
    highlight: Optional[str] = None,
    max_words: int = 5,
    max_chars: int = 26,
) -> Optional[str]:
    """Tulis file ASS untuk rentang klip. None bila tidak ada kata di rentang itu.

    Waktu kata sudah bertimestamp absolut (dari video sumber), jadi digeser ke 0
    sesuai `clip_start` supaya cocok dengan klip yang dirender.
    """
    words = extract_words(segments)
    if not words:
        return None

    end_limit = float(clip_end) if clip_end is not None else float("inf")
    clipped = [
        Word(
            text=w.text,
            start=max(0.0, w.start - clip_start),
            end=max(0.0, min(w.end, end_limit) - clip_start),
        )
        for w in words
        if w.end > clip_start and w.start < end_limit
    ]
    clipped = [w for w in clipped if w.end > w.start]
    if not clipped:
        return None

    style = _parse_force_style(force_style)
    font_name = style.get("FontName") or "DejaVu Sans"
    font_size = _scaled(style.get("FontSize", "16"), height, 16)
    primary = style.get("PrimaryColour") or "&H00FFFFFF"
    outline_colour = style.get("OutlineColour") or "&H00000000"
    back_colour = style.get("BackColour") or "&H00000000"
    border_style = int(style.get("BorderStyle", "1") or 1)
    bold = -1 if str(style.get("Bold", "0")).strip() not in {"0", "", "False"} else 0
    outline = _scaled(style.get("Outline", "1.6"), height, 1.6)
    shadow = _scaled(style.get("Shadow", "0"), height, 0)
    alignment = int(style.get("Alignment", "2") or 2)
    margin_v = _scaled(style.get("MarginV", "22"), height, 22)
    highlight = highlight or pick_highlight(primary)

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {int(width)}",
        f"PlayResY: {int(height)}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Cap,{font_name},{font_size},{primary},{primary},"
            f"{outline_colour},{back_colour},{bold},0,0,0,100,100,0,0,"
            f"{border_style},{outline},{shadow},{alignment},60,60,{margin_v},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: List[str] = []
    for cue in group_into_cues(clipped, max_words=max_words, max_chars=max_chars):
        for index, word in enumerate(cue):
            start = cue[0].start if index == 0 else word.start
            if index + 1 < len(cue):
                end = cue[index + 1].start
            else:
                end = cue[-1].end + 0.22
            if end - start < 0.08:
                end = start + 0.08
            text = _cue_text(cue, active=index, highlight=highlight)
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{text}"
            )

    if not events:
        return None

    Path(output_path).write_text("\n".join(header + events) + "\n", encoding="utf-8")
    return output_path
