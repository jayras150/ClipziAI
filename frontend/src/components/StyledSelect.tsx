"use client"

import { useEffect, useRef, useState } from "react"

export type StyledSelectOption = { value: string; label: string }

/**
 * Dropdown ber-style (bukan <select> native).
 *
 * Dipakai untuk memilih posisi caption thumbnail: tombol + panel yang bisa
 * ditutup dengan Escape / klik luar, mendukung navigasi keyboard.
 */
export default function StyledSelect({
  value,
  options,
  onChange,
  label,
  placeholder = "Select…",
  disabled = false,
}: {
  value: string
  options: StyledSelectOption[]
  onChange: (value: string) => void
  label?: string
  placeholder?: string
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const current = options.find((option) => option.value === value)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onPointerDown)
    document.addEventListener("touchstart", onPointerDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onPointerDown)
      document.removeEventListener("touchstart", onPointerDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  return (
    <div className="cs-select" ref={wrapRef}>
      {label ? <span className="cs-select-label">{label}</span> : null}
      <button
        type="button"
        className="cs-select-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="cs-select-value">{current?.label || placeholder}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open ? (
        <div className="cs-select-panel" role="listbox">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              className={`cs-select-option${option.value === value ? " is-active" : ""}`}
              onClick={() => {
                onChange(option.value)
                setOpen(false)
              }}
            >
              {option.label}
              {option.value === value ? <span className="cs-select-check">✓</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
