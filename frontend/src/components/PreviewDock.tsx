"use client"

import { useEffect, useState } from "react"
import { Eye, EyeOff } from "lucide-react"

import EditingPreview, { type EditingPreviewProps } from "@/components/EditingPreview"

const STORAGE_KEY = "clipzi.preview.open"

/**
 * Kartu pratinjau melayang di kanan-bawah layar.
 *
 * Selalu terlihat saat scroll, bisa ditutup/dibuka (tersimpan di localStorage),
 * dan otomatis disembunyikan saat ada modal (clip popup / confirm dialog).
 */
export default function PreviewDock(props: EditingPreviewProps) {
  const [open, setOpen] = useState(false)
  const [ready, setReady] = useState(false)

  // Preferensi dibaca setelah mount (localStorage tidak ada di server).
  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    // Default terbuka supaya user melihat hasil setting sebelum mulai render.
    setOpen(saved === null ? true : saved === "1")
    setReady(true)
  }, [])

  useEffect(() => {
    if (!ready) return
    window.localStorage.setItem(STORAGE_KEY, open ? "1" : "0")
  }, [open, ready])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open])

  if (!ready) return null

  return (
    <aside className={`preview-dock${open ? " open" : ""}`} aria-label="Live editing preview">
      {open ? (
        <div className="preview-dock-card">
          <div className="preview-dock-head">
            <span className="preview-dock-title">
              <Eye size={13} /> Preview
            </span>
            <button
              type="button"
              className="preview-dock-btn"
              onClick={() => setOpen(false)}
              aria-label="Hide live preview"
            >
              <EyeOff size={14} />
            </button>
          </div>
          <EditingPreview {...props} />
        </div>
      ) : (
        <button
          type="button"
          className="preview-dock-fab"
          onClick={() => setOpen(true)}
          aria-expanded={false}
          aria-label="Show live preview"
        >
          <Eye size={16} />
          <span>Preview</span>
        </button>
      )}
    </aside>
  )
}
