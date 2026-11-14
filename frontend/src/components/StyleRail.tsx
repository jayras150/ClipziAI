"use client"

import { useEffect, useRef } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { subtitlePreviewStyle, type SubtitleStyleOption } from "@/lib/caption-styles"

/**
 * Deretan kartu gaya subtitle yang bisa digeser kiri/kanan.
 *
 * - Drag dengan mouse (pointer events) + scroll native di perangkat sentuh.
 * - Tombol panah, snap per kartu, dan keyboard ←/→.
 * - Kartu terpilih otomatis di tengah supaya selalu terlihat.
 */
export default function StyleRail({
  options,
  value,
  previewText,
  onChange,
}: {
  options: SubtitleStyleOption[]
  value: string
  previewText: string
  onChange: (value: string) => void
}) {
  const railRef = useRef<HTMLDivElement>(null)
  const drag = useRef({ active: false, startX: 0, startLeft: 0, moved: false })

  useEffect(() => {
    const rail = railRef.current
    if (!rail) return
    const selected = rail.querySelector<HTMLElement>(".style-card.selected")
    if (!selected) return
    const left = selected.offsetLeft - (rail.clientWidth - selected.clientWidth) / 2
    rail.scrollTo({ left: Math.max(0, left), behavior: "smooth" })
  }, [value])

  const scrollByPage = (direction: number) => {
    const rail = railRef.current
    if (!rail) return
    rail.scrollBy({ left: direction * Math.max(180, rail.clientWidth * 0.8), behavior: "smooth" })
  }

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const rail = railRef.current
    if (!rail || event.pointerType === "touch") return
    drag.current = { active: true, startX: event.clientX, startLeft: rail.scrollLeft, moved: false }
    rail.classList.add("dragging")
    rail.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const rail = railRef.current
    if (!rail || !drag.current.active) return
    const dx = event.clientX - drag.current.startX
    if (Math.abs(dx) > 6) drag.current.moved = true
    rail.scrollLeft = drag.current.startLeft - dx
  }

  const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const rail = railRef.current
    if (!rail) return
    if (drag.current.active) {
      try {
        rail.releasePointerCapture(event.pointerId)
      } catch {
        /* pointer sudah lepas */
      }
    }
    drag.current.active = false
    rail.classList.remove("dragging")
    if (drag.current.moved) {
      // Biarkan click yang menyusul tetap diblokir, lalu reset.
      window.setTimeout(() => {
        drag.current.moved = false
      }, 0)
    }
  }

  const onClickCapture = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!drag.current.moved) return
    event.preventDefault()
    event.stopPropagation()
    drag.current.moved = false
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return
    event.preventDefault()
    const index = Math.max(
      0,
      options.findIndex((option) => option.value === value),
    )
    const next = Math.min(
      options.length - 1,
      Math.max(0, index + (event.key === "ArrowRight" ? 1 : -1)),
    )
    const option = options[next]
    if (option) onChange(option.value)
  }

  return (
    <div className="style-rail-wrap">
      <button
        type="button"
        className="style-rail-nav"
        onClick={() => scrollByPage(-1)}
        aria-label="Previous subtitle styles"
      >
        <ChevronLeft size={16} />
      </button>

      <div
        className="style-rail"
        ref={railRef}
        role="radiogroup"
        aria-label="Subtitle style"
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onClickCapture={onClickCapture}
        onKeyDown={onKeyDown}
      >
        {options.map((option) => {
          const selected = value === option.value
          return (
            <button
              key={option.value || "default"}
              type="button"
              role="radio"
              aria-checked={selected}
              className={`style-card${selected ? " selected" : ""}`}
              onClick={() => onChange(option.value)}
            >
              <span className="style-card-label">{option.label}</span>
              <span className="style-card-preview" aria-hidden="true">
                <span style={subtitlePreviewStyle(option.value)}>{previewText}</span>
              </span>
            </button>
          )
        })}
      </div>

      <button
        type="button"
        className="style-rail-nav"
        onClick={() => scrollByPage(1)}
        aria-label="Next subtitle styles"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  )
}
