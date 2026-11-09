"use client"

import { useEffect, useState } from "react"
import Link from "next/link"

export default function Navbar() {
  // Status login dibaca di useEffect, BUKAN saat render: localStorage tidak ada
  // di server sehingga membacanya langsung akan memicu hydration mismatch.
  const [signedIn, setSignedIn] = useState(false)

  useEffect(() => {
    setSignedIn(Boolean(window.localStorage.getItem("token")))
  }, [])

  return (
    <header className="ui-container ui-nav">
      <Link className="ui-brand" href="/">
        <span className="ui-brand-mark">▶</span>
        <span>
          clipzy<em>AI</em>
        </span>
      </Link>
      <nav className="ui-nav-links">
        <Link href="/dashboard">Dashboard</Link>
        <Link href="/pricing">Pricing</Link>
        <Link href="/profile">Profile</Link>
        <Link href="/contact">Contact</Link>
      </nav>
      <div className="ui-nav-actions">
        {signedIn ? (
          <Link className="ui-btn ui-btn-gold" href="/dashboard">
            Open studio
          </Link>
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
