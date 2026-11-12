"use client"

/**
 * Spinner ClipzyAI (orbit / ring / dots).
 *
 * Animasi murni CSS (`cz-*` di theme.css) sehingga ringan, tidak butuh library
 * tambahan, dan menghormati `prefers-reduced-motion`.
 *
 * - `orbit` : dua cincin berputar berlawanan arah + inti berdenyut + satelit.
 * - `ring`  : cincin tunggal (untuk di dalam tombol).
 * - `dots`  : tiga titik memantul (untuk teks inline).
 */
type Variant = "orbit" | "ring" | "dots"
type Size = "xs" | "sm" | "md" | "lg" | "xl"

const RING_WIDTH: Record<Size, string> = {
  xs: "1px",
  sm: "1.5px",
  md: "2px",
  lg: "2.5px",
  xl: "3px",
}

export function ClipzySpinner({
  size = "md",
  variant = "orbit",
  className = "",
  label = "Memproses",
}: {
  size?: Size
  variant?: Variant
  className?: string
  label?: string
}) {
  const classes = `cz-spinner cz-spinner--${size} ${className}`.trim()

  if (variant === "dots") {
    return (
      <span role="status" aria-label={label} className="cz-spinner cz-spinner--dots">
        <span />
        <span />
        <span />
      </span>
    )
  }

  if (variant === "ring") {
    return (
      <span
        role="status"
        aria-label={label}
        className={classes}
        style={{ ["--cz-ring-width" as string]: RING_WIDTH[size] }}
      >
        <span className="cz-spinner__ring" />
        <span className="cz-spinner__arc" />
      </span>
    )
  }

  return (
    <span
      role="status"
      aria-label={label}
      className={classes}
      style={{ ["--cz-ring-width" as string]: RING_WIDTH[size] }}
    >
      <span className="cz-spinner__orbit" />
      <span className="cz-spinner__orbit cz-spinner__orbit--reverse" />
      <span className="cz-spinner__core" />
      <span className="cz-spinner__dot" />
    </span>
  )
}

/** Spinner mini untuk di dalam badge/teks. */
export function InlineSpinner({ className = "" }: { className?: string }) {
  return <ClipzySpinner size="xs" variant="ring" className={`inline-block ${className}`} />
}

/**
 * Baris status proses dengan latar berkilau. Dipakai saat task sedang
 * queued/processing supaya pengguna tahu sistem masih bekerja.
 */
export function ProcessingBar({
  title,
  hint,
  progress,
}: {
  title: string
  hint?: string
  progress?: number
}) {
  return (
    <div className="cz-processing" style={{ color: "var(--ui-gold, #f4c76b)" }}>
      <ClipzySpinner size="sm" />
      <span className="cz-processing__label">
        <span style={{ color: "#f4efe4", fontWeight: 600 }}>{title}</span>
        {hint ? <span className="cz-processing__hint">{hint}</span> : null}
      </span>
      {typeof progress === "number" ? (
        <span style={{ marginLeft: "auto", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
          {Math.round(progress)}%
        </span>
      ) : null}
    </div>
  )
}
