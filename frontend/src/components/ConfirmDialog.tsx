"use client"

import { useEffect } from "react"
import { AlertTriangle, LoaderCircle } from "lucide-react"

/**
 * Dialog konfirmasi sederhana (bukan window.confirm) supaya aksi destruktif —
 * misalnya memutus koneksi YouTube — tidak pernah terjadi karena satu klik.
 */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  busy = false,
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  description: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  busy?: boolean
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  // Tutup dengan tombol Escape; jangan tutup saat proses sedang berjalan.
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, busy, onCancel])

  if (!open) return null

  return (
    <div
      className="ui-modal-backdrop"
      role="presentation"
      onClick={() => {
        if (!busy) onCancel()
      }}
    >
      <div
        className="ui-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ui-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="ui-modal-head">
          <span className={danger ? "ui-modal-icon danger" : "ui-modal-icon"}>
            <AlertTriangle size={17} />
          </span>
          <h3 className="ui-subtitle" id="ui-modal-title" style={{ margin: 0 }}>
            {title}
          </h3>
        </div>
        <div className="ui-muted" style={{ marginTop: 12, fontSize: 14, lineHeight: 1.55 }}>
          {description}
        </div>
        <div className="ui-modal-actions">
          <button type="button" className="ui-btn ui-btn-ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={danger ? "ui-btn ui-btn-danger" : "ui-btn ui-btn-gold"}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy && <LoaderCircle size={15} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
