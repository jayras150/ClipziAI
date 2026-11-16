/**
 * 50 gaya caption thumbnail (id sama dengan backend caption_catalog.py).
 * `css` menunjuk kelas preview di theme.css.
 */
export type ThumbnailCaptionStyle = { id: string; label: string; css: string }

export const THUMBNAIL_CAPTION_STYLES: ThumbnailCaptionStyle[] = [
  { id: "cyber-glitch", label: "CYBER GLITCH", css: "cap-cyber-glitch" },
  { id: "acid-lime", label: "ACID LIME", css: "cap-acid-lime" },
  { id: "hormozi-pop", label: "HORMOZI POP", css: "cap-hormozi-pop" },
  { id: "comic-boom", label: "COMIC BOOM", css: "cap-comic-boom" },
  { id: "retro-vhs", label: "RETRO VHS", css: "cap-retro-vhs" },
  { id: "luxury-serif", label: "LUXURY SERIF", css: "cap-luxury-serif" },
  { id: "gradient-fire", label: "GRADIENT FIRE", css: "cap-gradient-fire" },
  { id: "3d-extrude", label: "3D EXTRUDE", css: "cap-3d-extrude" },
  { id: "glass-pill", label: "GLASS PILL", css: "cap-glass-pill" },
  { id: "cinematic", label: "CINEMATIC", css: "cap-cinematic" },
  { id: "8bit-arcade", label: "8-BIT ARCADE", css: "cap-8bit-arcade" },
  { id: "marker-brush", label: "MARKER BRUSH", css: "cap-marker-brush" },
  { id: "cyber-orbit", label: "CYBER ORBIT", css: "cap-cyber-orbit" },
  { id: "manga-slash", label: "MANGA SLASH", css: "cap-manga-slash" },
  { id: "neon-sakura", label: "NEON SAKURA", css: "cap-neon-sakura" },
  { id: "highlighter", label: "HIGHLIGHTER", css: "cap-highlighter" },
  { id: "matrix-code", label: "MATRIX CODE", css: "cap-matrix-code" },
  { id: "wanted-poster", label: "WANTED", css: "cap-wanted-poster" },
  { id: "holo-chrome", label: "HOLO CHROME", css: "cap-holo-chrome" },
  { id: "blood-horror", label: "HORROR GLITCH", css: "cap-blood-horror" },
  { id: "sunset-vapor", label: "SUNSET VAPOR", css: "cap-sunset-vapor" },
  { id: "hollow-neon", label: "HOLLOW NEON", css: "cap-hollow-neon" },
  { id: "breaking-news", label: "NEWS ALERT", css: "cap-breaking-news" },
  { id: "mint-bubble", label: "MINT BUBBLE", css: "cap-mint-bubble" },
  { id: "army-stencil", label: "ARMY STENCIL", css: "cap-army-stencil" },
  { id: "zombie-drip", label: "ZOMBIE DRIP", css: "cap-zombie-drip" },
  { id: "disco-neon", label: "DISCO NEON", css: "cap-disco-neon" },
  { id: "typewriter", label: "TYPEWRITER", css: "cap-typewriter" },
  { id: "bubble-gum", label: "BUBBLE GUM", css: "cap-bubble-gum" },
  { id: "retro-script", label: "RETRO SCRIPT", css: "cap-retro-script" },
  { id: "brutalist", label: "BRUTALIST", css: "cap-brutalist" },
  { id: "hand-note", label: "HAND NOTE", css: "cap-hand-note" },
  { id: "pixel-mini", label: "PIXEL MINI", css: "cap-pixel-mini" },
  { id: "western-slab", label: "WESTERN SLAB", css: "cap-western-slab" },
  { id: "aurora-glow", label: "AURORA GLOW", css: "cap-aurora-glow" },
  { id: "vintage-script", label: "VINTAGE SCRIPT", css: "cap-vintage-script" },
  { id: "lyric-green", label: "LYRIC GREEN", css: "cap-lyric-green" },
  { id: "rgb-split", label: "RGB SPLIT", css: "cap-rgb-split" },
  { id: "red-badge", label: "RED BADGE", css: "cap-red-badge" },
  { id: "gold-foil", label: "GOLD FOIL", css: "cap-gold-foil" },
  { id: "ice-frost", label: "ICE FROST", css: "cap-ice-frost" },
  { id: "lava-crack", label: "LAVA CRACK", css: "cap-lava-crack" },
  { id: "press-cut", label: "PRESS CUT", css: "cap-press-cut" },
  { id: "caution", label: "CAUTION", css: "cap-caution" },
  { id: "velvet-royal", label: "VELVET ROYAL", css: "cap-velvet-royal" },
  { id: "electric-volt", label: "ELECTRIC VOLT", css: "cap-electric-volt" },
  { id: "inverted-mix", label: "INVERTED MIX", css: "cap-inverted-mix" },
  { id: "tokyo-neon", label: "TOKYO NEON", css: "cap-tokyo-neon" },
  { id: "toxic-slime", label: "TOXIC SLIME", css: "cap-toxic-slime" },
  { id: "minimal-badge", label: "MINIMAL PILL", css: "cap-minimal-badge" },
]

export const THUMBNAIL_CAPTION_ANCHORS = [
  "top-left","top-center","top-right",
  "center-left","center","center-right",
  "bottom-left","bottom-center","bottom-right",
] as const

export const DEFAULT_CAPTION_STYLE = "hormozi-pop"
export const DEFAULT_CAPTION_POSITION = "bottom-center"
