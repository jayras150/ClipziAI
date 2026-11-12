"use client"

import { useEffect, useState } from "react"
import Link from "next/link"

import UserMenu from "@/components/UserMenu"
import { AUTH_EVENT, hasSession } from "@/lib/auth"
import { getApiBaseUrl } from "@/lib/env"

type Branding = { app_name?: string; logo_url?: string | null }

export default function Navbar() {
  // Status login dibaca di useEffect, BUKAN saat render: localStorage tidak ada
  // di server sehingga membacanya langsung akan memicu hydration mismatch.
  const [signedIn, setSignedIn] = useState(false)
  const [branding, setBranding] = useState<Branding | null>(null)

  useEffect(() => {
    const sync = () => setSignedIn(hasSession())
    sync()
    // Ikut berubah saat tab lain login/logout/refresh (storage + BroadcastChannel).
    window.addEventListener("storage", sync)
    window.addEventListener(AUTH_EVENT, sync)
    return () => {
      window.removeEventListener("storage", sync)
      window.removeEventListener(AUTH_EVENT, sync)
    }
  }, [])

  // Branding (nama + logo) diatur admin; diambil sekali saat mount.
  useEffect(() => {
    let cancelled = false
    fetch(getApiBaseUrl() + "/api/branding")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!cancelled && data) setBranding(data as Branding)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const appName = branding?.app_name || "Clipzy AI"

  return (
    <header className="ui-container ui-nav">
      <Link className="ui-brand" href="/">
        {branding?.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="ui-brand-logo" src={branding.logo_url} alt={appName} />
        ) : (
          <span className="ui-brand-mark">▶</span>
        )}
        <span>{appName}</span>
      </Link>
      <nav className="ui-nav-links">
        <Link href="/dashboard">Dashboard</Link>
        <Link href="/#features">Features</Link>
        <Link href="/#how">How it works</Link>
        <Link href="/#demo">Demo</Link>
        <Link href="/pricing">Pricing</Link>
        <Link href="/contact">Contact</Link>
      </nav>
      <div className="ui-nav-actions">
        {signedIn ? (
          <UserMenu />
        ) : (
          <>
            <Link className="ui-btn ui-btn-ghost" href="/login">
              Sign in
            </Link>
            <Link className="ui-btn ui-btn-gold" href="/register">
              Start free
            </Link>
          </>
        )}
      </div>
    </header>
  )
}
