"use client"

import { captionAnchor, subtitlePreviewStyle } from "@/lib/caption-styles"

/**
 * Kartu pratinjau: menampilkan frame video/foto klip dengan caption dirender
 * memakai preset subtitle yang sedang dipilih, supaya pengguna melihat hasil
 * akhirnya sebelum render (bukan hanya kotak teks kecil).
 */
export default function SubtitlePreview({
  style,
  caption,
  poster,
}: {
  style: string
  caption: string
  poster?: string | null
}) {
  const anchor = captionAnchor(style)
  const text = (caption || "Sample caption").slice(0, 80)

  return (
    <div className="subtitle-preview">
      <div
        className="subtitle-preview-frame"
        style={
          poster
            ? { backgroundImage: `url(${poster})` }
            : {
                backgroundImage:
                  "radial-gradient(120% 90% at 50% 0%, #263041, #080b12 70%)",
              }
        }
      >
        <span className="subtitle-preview-badge">Live preview</span>
        <span className={`subtitle-preview-caption ${anchor}`} style={subtitlePreviewStyle(style)}>
          {text}
        </span>
      </div>
      <p className="ui-hint" style={{ marginTop: 8 }}>
        Captions are burned into the video using this style (same as the rendered output).
      </p>
    </div>
  )
}
