"use client"

/** Dialog peringatan dengan aksi opsional (mis. tombol verifikasi channel). */
export default function AlertDialog({
  open,
  title,
  message,
  detail,
  actionLabel,
  actionHref,
  onClose,
}: {
  open: boolean
  title: string
  message: string
  detail?: string
  actionLabel?: string
  actionHref?: string
  onClose: () => void
}) {
  if (!open) return null

  return (
    <div className="cs-alert-backdrop" role="dialog" aria-modal="true" aria-labelledby="csAlertTitle">
      <div className="cs-alert-card">
        <div className="cs-alert-icon" aria-hidden="true">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M12 8v5" />
            <path d="M12 17h.01" />
            <circle cx="12" cy="12" r="9" />
          </svg>
        </div>
        <h3 id="csAlertTitle" className="cs-alert-title">
          {title}
        </h3>
        <p className="cs-alert-text">{message}</p>
        {detail ? <p className="cs-alert-detail">{detail}</p> : null}
        <div className="cs-alert-actions">
          {actionHref && actionLabel ? (
            <a
              className="ui-btn ui-btn-gold"
              href={actionHref}
              target="_blank"
              rel="noopener noreferrer"
              onClick={onClose}
            >
              {actionLabel}
            </a>
          ) : null}
          <button type="button" className="ui-btn ui-btn-ghost" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}
