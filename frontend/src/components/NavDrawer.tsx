"use client"

import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import Link from "next/link"
import { X } from "lucide-react"

import { APP_NAV_LINKS } from "@/lib/nav"

/** Ikon menu (SVG yang diminta): panel kiri dengan garis pemisah. */
function PanelIcon({ size = 20 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      aria-hidden="true"
    >
      <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
        <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
        <path d="M9 3v18" />
      </g>
    </svg>
  )
}

/**
 * Tombol menu + drawer kiri untuk mobile.
 *
 * - Hanya tampil ≤920px (desktop tetap memakai menu horizontal).
 * - Drawer selebar setengah layar; klik di luar (backdrop) atau Escape menutup.
 * - Dirender lewat portal ke <body> supaya tidak terpengaruh backdrop-filter navbar.
 */
export default function NavDrawer({ activeHref }: { activeHref?: string }) {
  const [open, setOpen] = useState(false)
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", onKey)
    document.body.classList.add("drawer-open")
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.classList.remove("drawer-open")
    }
  }, [open])

  return (
    <>
      <button
        type="button"
        className="ui-nav-toggle"
        onClick={() => setOpen(true)}
        aria-label="Open menu"
        aria-expanded={open}
        aria-controls="app-drawer"
      >
        <PanelIcon />
      </button>

      {mounted &&
        open &&
        createPortal(
          <div
            className="ui-drawer-backdrop"
            role="presentation"
            onClick={() => setOpen(false)}
          >
            <aside
              className="ui-drawer"
              id="app-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Menu"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="ui-drawer-head">
                <span className="ui-drawer-title">Menu</span>
                <button
                  type="button"
                  className="ui-drawer-close"
                  onClick={() => setOpen(false)}
                  aria-label="Close menu"
                >
                  <X size={16} />
                </button>
              </div>
              <nav className="ui-drawer-links">
                {APP_NAV_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setOpen(false)}
                    className={activeHref === link.href ? "active" : undefined}
                  >
                    {link.label}
                  </Link>
                ))}
              </nav>
            </aside>
          </div>,
          document.body,
        )}
    </>
  )
}
