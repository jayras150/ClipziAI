"""Katalog 50 gaya caption thumbnail (id & label sama dengan UI carousel).

Setiap entri menyimpan parameter render Pillow: font, ukuran relatif, warna,
background/pill, stroke, shadow, rotasi, gradient, dan posisi default.
"""
from __future__ import annotations

from typing import Any, Dict, List

FONT_FILES = {
    "inter": "Inter-Bold.ttf",
    "anton": "Anton-Regular.ttf",
    "bangers": "Bangers-Regular.ttf",
    "bebas": "BebasNeue-Regular.ttf",
    "blackops": "BlackOpsOne-Regular.ttf",
    "caveat": "Caveat-Bold.ttf",
    "cinzel": "Cinzel-Bold.ttf",
    "creepster": "Creepster-Regular.ttf",
    "fredoka": "Fredoka-Bold.ttf",
    "jetbrains": "JetBrainsMono-Bold.ttf",
    "lobster": "Lobster-Regular.ttf",
    "monoton": "Monoton-Regular.ttf",
    "orbitron": "Orbitron-Bold.ttf",
    "oswald": "Oswald-Bold.ttf",
    "pacifico": "Pacifico-Regular.ttf",
    "marker": "PermanentMarker-Regular.ttf",
    "playfair": "PlayfairDisplay-Bold.ttf",
    "pressstart": "PressStart2P-Regular.ttf",
    "righteous": "Righteous-Regular.ttf",
    "glitch": "RubikGlitch-Regular.ttf",
    "silkscreen": "Silkscreen-Bold.ttf",
    "special": "SpecialElite-Regular.ttf",
    "syne": "Syne-Bold.ttf",
    "ultra": "Ultra-Regular.ttf",
}


def _style(
    label: str,
    font: str = "inter",
    size: float = 0.075,
    color: str = "#FFFFFF",
    *,
    bg: str | None = None,
    radius: int = 10,
    pad: int = 18,
    stroke: int = 0,
    stroke_color: str = "#000000",
    shadow: int = 0,
    uppercase: bool = False,
    rotate: int = 0,
    gradient: List[str] | None = None,
    gradient_vertical: bool = False,
    position: str = "bottom-center",
    highlight: str | None = None,
) -> Dict[str, Any]:
    return {
        "label": label,
        "font": font,
        "size": size,
        "color": color,
        "bg": bg,
        "radius": radius,
        "pad": pad,
        "stroke": stroke,
        "stroke_color": stroke_color,
        "shadow": shadow,
        "uppercase": uppercase,
        "rotate": rotate,
        "gradient": gradient,
        "gradient_vertical": gradient_vertical,
        "position": position,
        "highlight": highlight,
    }


CAPTION_STYLES: Dict[str, Dict[str, Any]] = {
    "cyber-glitch": _style("CYBER GLITCH", "glitch", 0.078, "#FFFFFF", stroke=2, stroke_color="#FF0055", shadow=2),
    "acid-lime": _style("ACID LIME", "anton", 0.082, "#090B10", bg="#CCFF00", radius=6, rotate=-3, uppercase=True),
    "hormozi-pop": _style("HORMOZI POP", "anton", 0.088, "#FFFFFF", stroke=2, uppercase=True, highlight="#00FF66"),
    "comic-boom": _style("COMIC BOOM", "bangers", 0.094, "#FFDE00", stroke=2, stroke_color="#000000", shadow=3),
    "retro-vhs": _style("RETRO VHS", "jetbrains", 0.068, "#FF71CE", bg="#01324A", stroke=1, stroke_color="#01CDFE"),
    "luxury-serif": _style("LUXURY SERIF", "playfair", 0.078, "#F6C25B", gradient=["#FFF6B7", "#F6C25B", "#C88A2B"], shadow=2),
    "gradient-fire": _style("GRADIENT FIRE", "inter", 0.076, "#FF9500", gradient=["#FF3B30", "#FF9500", "#FFCC00"], uppercase=True, shadow=2),
    "3d-extrude": _style("3D EXTRUDE", "anton", 0.082, "#FFFFFF", shadow=4, stroke=1, stroke_color="#5B21B6"),
    "glass-pill": _style("GLASS PILL", "inter", 0.066, "#E0F2FE", bg="#1E3A5F", radius=999, pad=22),
    "cinematic": _style("CINEMATIC", "cinzel", 0.062, "#F8FAFC", uppercase=True, shadow=2),
    "8bit-arcade": _style("8-BIT ARCADE", "pressstart", 0.05, "#4ADE80", bg="#0B1F17", stroke=2, stroke_color="#064E3B"),
    "marker-brush": _style("MARKER BRUSH", "marker", 0.088, "#FFFFFF", rotate=-4, shadow=4, stroke_color="#EC4899"),
    "cyber-orbit": _style("CYBER ORBIT", "orbitron", 0.062, "#38BDF8", stroke=1, stroke_color="#38BDF8", shadow=2, uppercase=True),
    "manga-slash": _style("MANGA SLASH", "anton", 0.082, "#000000", bg="#FFFFFF", radius=2, rotate=-2, uppercase=True),
    "neon-sakura": _style("NEON SAKURA", "inter", 0.072, "#FBCFE8", shadow=4, stroke_color="#DB2777"),
    "highlighter": _style("HIGHLIGHTER", "oswald", 0.08, "#FFFFFF", highlight="#FACC15"),
    "matrix-code": _style("MATRIX CODE", "jetbrains", 0.062, "#22C55E", bg="#0E2A1C", stroke=1, stroke_color="#22C55E"),
    "wanted-poster": _style("WANTED", "cinzel", 0.07, "#451A03", bg="#FDE68A", stroke=1, stroke_color="#92400E", uppercase=True),
    "holo-chrome": _style("HOLO CHROME", "bebas", 0.095, "#E2E8F0", gradient=["#FFFFFF", "#94A3B8", "#334155", "#E2E8F0"], uppercase=True, shadow=2),
    "blood-horror": _style("HORROR GLITCH", "glitch", 0.078, "#EF4444", shadow=4, stroke_color="#991B1B"),
    "sunset-vapor": _style("SUNSET VAPOR", "oswald", 0.078, "#C084FC", gradient=["#F43F5E", "#C084FC", "#38BDF8"], uppercase=True),
    "hollow-neon": _style("HOLLOW NEON", "anton", 0.088, "#38BDF8", stroke=3, stroke_color="#38BDF8", uppercase=True),
    "breaking-news": _style("NEWS ALERT", "oswald", 0.07, "#FFFFFF", bg="#DC2626", radius=4, uppercase=True),
    "mint-bubble": _style("MINT BUBBLE", "inter", 0.066, "#064E3B", bg="#6EE7B7", radius=999, pad=20),
}


_MORE = {
    "army-stencil": _style("ARMY STENCIL", "blackops", 0.072, "#BEF264", bg="#365314", stroke=1, stroke_color="#A3E635"),
    "zombie-drip": _style("ZOMBIE DRIP", "creepster", 0.098, "#84CC16", shadow=4),
    "disco-neon": _style("DISCO NEON", "monoton", 0.07, "#F472B6", shadow=4, stroke_color="#A855F7"),
    "typewriter": _style("TYPEWRITER", "special", 0.066, "#1C1917", bg="#F5F5F4", radius=4, shadow=2),
    "bubble-gum": _style("BUBBLE GUM", "fredoka", 0.074, "#FFFFFF", bg="#FF758C", radius=999, pad=22),
    "retro-script": _style("RETRO SCRIPT", "pacifico", 0.082, "#FDE047", shadow=3, stroke_color="#EA580C"),
    "brutalist": _style("BRUTALIST", "syne", 0.066, "#000000", bg="#FFFFFF", radius=2, uppercase=True),
    "hand-note": _style("HAND NOTE", "caveat", 0.1, "#38BDF8", shadow=1),
    "pixel-mini": _style("PIXEL MINI", "silkscreen", 0.056, "#FEF08A", bg="#1E1B4B", stroke=1, stroke_color="#818CF8"),
    "western-slab": _style("WESTERN SLAB", "ultra", 0.068, "#FBBF24", stroke=2, stroke_color="#451A03"),
    "aurora-glow": _style("AURORA GLOW", "righteous", 0.078, "#34D399", gradient=["#34D399", "#38BDF8", "#A78BFA"], shadow=3),
    "vintage-script": _style("VINTAGE SCRIPT", "lobster", 0.086, "#FDA4AF", shadow=2, stroke_color="#881337"),
    "lyric-green": _style("LYRIC GREEN", "inter", 0.062, "#000000", bg="#1DB954", radius=8, pad=18),
    "rgb-split": _style("RGB SPLIT", "inter", 0.076, "#FFFFFF", stroke=2, stroke_color="#FE2C55", shadow=2),
    "red-badge": _style("RED BADGE", "oswald", 0.072, "#FFFFFF", bg="#FF0000", radius=6, uppercase=True),
    "gold-foil": _style("GOLD FOIL", "cinzel", 0.072, "#FEF08A", stroke=1, stroke_color="#EAB308", uppercase=True),
    "ice-frost": _style("ICE FROST", "orbitron", 0.066, "#E0F2FE", shadow=4, stroke_color="#0284C7"),
    "lava-crack": _style("LAVA CRACK", "anton", 0.082, "#FEF08A", bg="#7F1D1D", stroke=1, stroke_color="#F97316"),
    "press-cut": _style("PRESS CUT", "playfair", 0.068, "#090B10", bg="#E7E5E4", radius=2, rotate=2),
    "caution": _style("CAUTION", "jetbrains", 0.06, "#FACC15", bg="#18181B", stroke=1, stroke_color="#FACC15", uppercase=True),
    "velvet-royal": _style("VELVET ROYAL", "playfair", 0.074, "#F3E8FF", bg="#581C87", radius=8, pad=18),
    "electric-volt": _style("ELECTRIC VOLT", "anton", 0.082, "#FDE047", stroke=2, stroke_color="#1D4ED8", shadow=3),
    "inverted-mix": _style("INVERTED MIX", "inter", 0.07, "#FFFFFF", highlight="#FFFFFF"),
    "tokyo-neon": _style("TOKYO NEON", "oswald", 0.076, "#FFFFFF", stroke=2, stroke_color="#F43F5E", shadow=3),
    "toxic-slime": _style("TOXIC SLIME", "fredoka", 0.074, "#A3E635", bg="#1E1B4B", radius=12, pad=18),
    "minimal-badge": _style("MINIMAL PILL", "jetbrains", 0.062, "#CBD5E1", bg="#1E293B", radius=999, pad=20),
}

CAPTION_STYLES.update(_MORE)

__all__ = ["CAPTION_STYLES", "FONT_FILES"]
