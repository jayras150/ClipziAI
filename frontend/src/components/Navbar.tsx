"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

import { BrandLogo } from "@/components/BrandingProvider"
import UserMenu from "@/components/UserMenu"
import { AUTH_EVENT, hasSession } from "@/lib/auth"

/**
 * Navbar aplikasi.
 *
 * Logo + nama diambil dari `<BrandLogo />` (branding admin), bukan hardcode,
 * sehingga mengganti logo di dashboard langsung berlaku di semua halaman.
 */
export default function Navbar() {
  // Status login dibaca di useEffect, BUKAN saat render: localStorage tidak ada
  // di server sehingga membacanya langsung akan memicu hydration mismatch.
  const [signedIn, setSignedIn] = useState(false)

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

  return (
    <header className="ui-container ui-nav">
      <BrandLogo />
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
