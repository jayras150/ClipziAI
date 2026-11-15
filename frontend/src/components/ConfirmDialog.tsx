import { useEffect, useId, useRef } from "react"
import { AlertTriangle, LoaderCircle } from "lucide-react"

/**
 * Dialog konfirmasi milik aplikasi (pengganti `window.confirm`) supaya aksi
 * destruktif — misalnya menghapus project atau memutus koneksi YouTube — tidak
 * pernah terjadi karena satu klik.
 *
 * Catatan: file ini TIDAK memakai direktif `"use client"` karena selalu
 * dirender dari halaman yang sudah client (`dashboard`, `profile`). Tanpa
 * direktif, Next tidak menganggapnya "client entry" sehingga tidak
 * memunculkan warning `Props must be serializable` untuk `onConfirm`/`onCancel`.
 * Hook tetap aman karena modul ikut graph client milik halaman pemanggil.
 *
 * Perilaku: fokus awal di tombol batal, Escape/klik backdrop menutup (kecuali
 * sedang proses), scroll halaman dikunci, dan label terhubung ke `aria-*`.
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
  const titleId = useId()
  const descriptionId = useId()
  const cancelRef = useRef<HTMLButtonElement | null>(null)

  // Tutup dengan tombol Escape; jangan tutup saat proses sedang berjalan.
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, busy, onCancel])

  // Kunci scroll halaman selama dialog terbuka.
  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = previous
    }
  }, [open])

  // Fokus ke tombol batal: aksi destruktif tidak boleh terpicu oleh Enter.
  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => cancelRef.current?.focus(), 30)
    return () => window.clearTimeout(timer)
  }, [open])

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
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="ui-modal-head">
          <span className={danger ? "ui-modal-icon danger" : "ui-modal-icon"}>
            <AlertTriangle size={17} />
          </span>
          <h3 className="ui-subtitle" id={titleId} style={{ margin: 0 }}>
            {title}
          </h3>
        </div>
        <div
          className="ui-muted"
          id={descriptionId}
          style={{ marginTop: 12, fontSize: 14, lineHeight: 1.55 }}
        >
          {description}
        </div>
        <div className="ui-modal-actions">
          <button
            type="button"
            ref={cancelRef}
            className="ui-btn ui-btn-ghost"
            onClick={onCancel}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={danger ? "ui-btn ui-btn-danger" : "ui-btn ui-btn-gold"}
            onClick={onConfirm}
            disabled={busy}
            aria-busy={busy || undefined}
          >
            {busy && <LoaderCircle size={15} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

