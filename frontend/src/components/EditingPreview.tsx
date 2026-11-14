"use client"

import { AudioLines, Film, Layers, Music2, ScanFace, Scissors } from "lucide-react"

import {
  captionAnchor,
  filterPreviewStyle,
  subtitlePreviewStyle,
  watermarkAnchorStyle,
} from "@/lib/caption-styles"

export type EditingPreviewProps = {
  poster?: string | null
  caption: string
  captionStyle: string
  aspectRatio: string
  filterPreset: string
  blurFill: boolean
  watermarkUrl?: string
  watermarkPosition: string
  speed: string
  musicName?: string
  musicDucking?: boolean
  removeSilence: boolean
  cleanAudio: boolean
  autoZoom: string
  introUrl?: string
  outroUrl?: string
}

/**
 * Pratinjau kecil hasil kombinasi opsi editing.
 *
 * Semua fitur visual ditampilkan sekaligus: rasio, filter, blur-fill,
 * watermark (logo user / mark Clipzy), caption sesuai gaya yang dipilih,
 * plus badge untuk fitur non-visual (speed, musik, jump cuts, audio, zoom).
 */
export default function EditingPreview({
  poster,
  caption,
  captionStyle,
  aspectRatio,
  filterPreset,
  blurFill,
  watermarkUrl,
  watermarkPosition,
  speed,
  musicName,
  musicDucking,
  removeSilence,
  cleanAudio,
  autoZoom,
  introUrl,
  outroUrl,
}: EditingPreviewProps) {
  const anchor = captionAnchor(captionStyle)
  const text = (caption || "Sample caption").slice(0, 42)
  const hasPoster = Boolean(poster)
  const posterStyle = hasPoster ? { backgroundImage: `url(${poster})` } : undefined

  return (
    <div className="edit-preview">
      <div className="edit-preview-stage">
        <div className="edit-preview-frame" data-ratio={aspectRatio}>
          {blurFill && <div className="edit-preview-blur" style={posterStyle} />}
          <div
            className="edit-preview-media"
            data-filter={filterPreset}
            style={{ ...posterStyle, ...filterPreviewStyle(filterPreset) }}
          />
          <div className="edit-preview-shade" />

          {watermarkUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              className="edit-preview-wm"
              src={watermarkUrl}
              alt=""
              style={watermarkAnchorStyle(watermarkPosition)}
            />
          ) : (
            <span
              className="edit-preview-wm edit-preview-wm-mark"
              style={watermarkAnchorStyle(watermarkPosition)}
            >
              CLIPZY
            </span>
          )}

          <span
            className={`edit-preview-caption ${anchor}`}
            style={subtitlePreviewStyle(captionStyle, 0.62)}
          >
            {text}
          </span>
        </div>
      </div>

      <div className="edit-preview-chips">
        <span className="edit-preview-chip strong">{aspectRatio}</span>
        <span className="edit-preview-chip">{speed}×</span>
        <span className="edit-preview-chip">
          {filterPreset === "none" ? "no filter" : filterPreset}
        </span>
      </div>

      <div className="edit-preview-foot">
        <span className="edit-preview-music" title={musicName || "No music"}>
          <Music2 size={11} />
          <span>{musicName || "No music"}</span>
        </span>
        <span className="edit-preview-flags">
          {blurFill && <Layers size={12} aria-label="Blur-fill background" />}
          {removeSilence && <Scissors size={12} aria-label="Remove silence" />}
          {cleanAudio && <AudioLines size={12} aria-label="Clean audio" />}
          {musicDucking && musicName && <Music2 size={12} aria-label="Music ducking" />}
          {autoZoom !== "off" && <ScanFace size={12} aria-label="Auto zoom" />}
          {(introUrl || outroUrl) && <Film size={12} aria-label="Intro or outro" />}
        </span>
      </div>
    </div>
  )
}
