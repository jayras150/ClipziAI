"use client"

import Link from "next/link"

export default function Navbar() {
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
        <Link href="/contact">Contact</Link>
      </nav>
      <div className="ui-nav-actions">
        <Link className="ui-btn ui-btn-ghost" href="/login">
          Sign in
        </Link>
        <Link className="ui-btn ui-btn-gold" href="/register">
          Start free
        </Link>
      </div>
    </header>
  )
}
