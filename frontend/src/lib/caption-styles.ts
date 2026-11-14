/**
 * Preset gaya subtitle — satu sumber kebenaran untuk dashboard + preview.
 *
 * Nilai `value` harus sama dengan key `CAPTION_STYLES` di
 * `backend/app/services/processor.py`, supaya pratinjau = hasil render ffmpeg.
 */
export type SubtitleStyleOption = { value: string; label: string }

export const SUBTITLE_STYLE_OPTIONS: SubtitleStyleOption[] = [
  { value: "", label: "Default" },
  { value: "classic", label: "Classic white" },
  { value: "gold", label: "Bold gold" },
  { value: "boxed", label: "Black box" },
  { value: "neon", label: "Neon cyan" },
  { value: "top", label: "Clean top" },
  { value: "center", label: "Center hook" },
  { value: "karaoke", label: "Karaoke gold" },
  { value: "minimal", label: "Minimal clean" },
  { value: "impact", label: "Impact bold" },
  { value: "boxed_gold", label: "Gold on black" },
  { value: "pink", label: "Neon pink" },
  { value: "top_clean", label: "Headline top" },
  { value: "subtitle_bar", label: "Caption bar" },
]

const OUTLINE_DARK =
  "0 0 2px #000, 1px 1px 0 #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000"
const OUTLINE_THICK =
  "0 0 3px #000, 2px 2px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000"

/** Posisi vertikal caption (mengikuti Alignment di force_style backend). */
export function captionAnchor(style: string): "top" | "center" | "bottom" {
  if (style === "top" || style === "top_clean") return "top"
  if (style === "center") return "center"
  return "bottom"
}

export function subtitlePreviewStyle(style: string, scale = 1): React.CSSProperties {
  const base = subtitlePreviewStyleBase(style)
  if (scale === 1) return base

  const scaled: React.CSSProperties = { ...base }
  if (typeof scaled.fontSize === "number") {
    scaled.fontSize = Math.round(scaled.fontSize * scale * 10) / 10
  }
  if (typeof scaled.padding === "string") {
    scaled.padding = scaled.padding
      .split(" ")
      .map((part) =>
        part.endsWith("px") ? `${Math.round(parseFloat(part) * scale * 10) / 10}px` : part,
      )
      .join(" ")
  }
  if (typeof scaled.borderRadius === "number") {
    scaled.borderRadius = Math.round(scaled.borderRadius * scale * 10) / 10
  }
  if (typeof scaled.letterSpacing === "string" && scaled.letterSpacing.endsWith("px")) {
    scaled.letterSpacing = `${Math.round(parseFloat(scaled.letterSpacing) * scale * 10) / 10}px`
  }
  return scaled
}

/** Filter CSS yang meniru preset ffmpeg (untuk preview kecil di dashboard). */
export function filterPreviewStyle(preset: string): React.CSSProperties {
  switch (preset) {
    case "warm":
      return { filter: "sepia(0.32) saturate(1.35) contrast(1.05) brightness(1.03)" }
    case "cool":
      return { filter: "hue-rotate(-12deg) saturate(1.18) brightness(1.02)" }
    case "cinematic":
      return { filter: "contrast(1.18) saturate(0.9) brightness(0.95)" }
    case "bw":
      return { filter: "grayscale(1) contrast(1.12)" }
    case "vibrant":
      return { filter: "saturate(1.55) contrast(1.1)" }
    case "vintage":
      return { filter: "sepia(0.45) contrast(0.95) brightness(1.05) saturate(0.85)" }
    default:
      return {}
  }
}

/** Posisi watermark di dalam frame preview (mengikuti posisi overlay ffmpeg). */
export function watermarkAnchorStyle(position: string): React.CSSProperties {
  switch (position) {
    case "top-left":
      return { top: 6, left: 6 }
    case "top-right":
      return { top: 6, right: 6 }
    case "bottom-left":
      return { bottom: 26, left: 6 }
    case "center":
      return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" }
    case "bottom-right":
    default:
      return { bottom: 26, right: 6 }
  }
}

function subtitlePreviewStyleBase(style: string): React.CSSProperties {
  switch (style) {
    case "gold":
      return { color: "#f4c76b", fontSize: 17, fontWeight: 800, textShadow: OUTLINE_THICK }
    case "neon":
      return {
        color: "#7ce9dc",
        fontSize: 17,
        fontWeight: 800,
        textShadow: "0 0 8px rgba(124,233,220,.75), 1px 1px 0 #000",
      }
    case "boxed":
      return {
        color: "#ffffff",
        fontSize: 13,
        fontWeight: 700,
        background: "rgba(0,0,0,.78)",
        padding: "3px 8px",
        borderRadius: 3,
      }
    case "top":
      return { color: "#ffffff", fontSize: 14, fontWeight: 700, textShadow: OUTLINE_DARK }
    case "center":
      return { color: "#f4c76b", fontSize: 19, fontWeight: 800, textShadow: OUTLINE_THICK }
    case "classic":
      return { color: "#ffffff", fontSize: 14, fontWeight: 600, textShadow: OUTLINE_DARK }
    case "karaoke":
      return {
        fontSize: 18,
        fontWeight: 800,
        background: "linear-gradient(90deg,#ffffff 0 55%,#f4c76b 55% 100%)",
        WebkitBackgroundClip: "text",
        WebkitTextFillColor: "transparent",
      }
    case "minimal":
      return { color: "#f2f4f8", fontSize: 12, fontWeight: 500, textShadow: "0 1px 3px rgba(0,0,0,.65)" }
    case "impact":
      return {
        color: "#ffffff",
        fontSize: 21,
        fontWeight: 900,
        letterSpacing: "-0.5px",
        textTransform: "uppercase",
        textShadow: OUTLINE_THICK,
      }
    case "boxed_gold":
      return {
        color: "#f4c76b",
        fontSize: 14,
        fontWeight: 800,
        background: "rgba(0,0,0,.82)",
        padding: "3px 9px",
        borderRadius: 4,
      }
    case "pink":
      return {
        color: "#ff7bc0",
        fontSize: 17,
        fontWeight: 800,
        textShadow: "0 0 9px rgba(255,123,192,.8), 1px 1px 0 #1a0c14",
      }
    case "top_clean":
      return { color: "#ffffff", fontSize: 15, fontWeight: 800, textShadow: OUTLINE_DARK }
    case "subtitle_bar":
      return {
        color: "#ffffff",
        fontSize: 12,
        fontWeight: 700,
        background: "rgba(0,0,0,.72)",
        padding: "4px 12px",
        borderRadius: 8,
        width: "100%",
      }
    default:
      return { color: "#e8e9ee", fontSize: 13, fontWeight: 600 }
  }
}
