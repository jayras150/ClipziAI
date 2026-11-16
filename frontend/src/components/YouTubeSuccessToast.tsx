"use client"

import { useEffect, useState } from "react"

/** Toast sukses upload YouTube dengan animasi checkmark + sparks. */
export default function YouTubeSuccessToast({
  open,
  onClose,
  message = "Congratulations, the video has been successfully uploaded to YouTube.",
  hint,
}: {
  open: boolean
  onClose: () => void
  message?: string
  /** Baris kedua, mis. minta user menunggu proses YouTube. */
  hint?: string
}) {
  const [closing, setClosing] = useState(false)

  useEffect(() => {
    if (!open) {
      setClosing(false)
      return
    }
    const timer = window.setTimeout(() => setClosing(true), 10000)
    return () => window.clearTimeout(timer)
  }, [open])

  useEffect(() => {
    if (!closing) return
    const timer = window.setTimeout(() => {
      onClose()
      setClosing(false)
    }, 340)
    return () => window.clearTimeout(timer)
  }, [closing, onClose])

  if (!open) return null

  return (
    <div className={`yt-toast-wrapper${closing ? " is-closing" : ""}`} id="ytToastCard">
      <div className="yt-toast-glow" />
      <div className="yt-toast-card">
        <div className="yt-toast-shimmer" />
        <div className="yt-icon-box">
          <div className="yt-pulse-ring" />
          <span className="yt-spark yt-spark-1" />
          <span className="yt-spark yt-spark-2" />
          <span className="yt-spark yt-spark-3" />
          <svg className="yt-check-svg" viewBox="0 0 24 24" fill="none">
            <path
              className="yt-check-path"
              d="M5 13l4 4L19 7"
              stroke="#10b981"
              strokeWidth={2.75}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="yt-toast-text">
          <p className="yt-toast-message">{message}</p>
          {hint ? <p className="yt-toast-hint">{hint}</p> : null}
        </div>
        <button
          type="button"
          className="yt-close-btn"
          aria-label="Close notification"
          onClick={() => setClosing(true)}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}
