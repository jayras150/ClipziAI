"use client"

import Link from "next/link"
import { BrandLogo, BrandName } from "@/components/BrandingProvider"

/**
 * Footer bersama untuk halaman aplikasi & legal.
 * Bahasa Inggris sesuai permintaan; link mengarah ke halaman legal yang nyata.
 */
export default function SiteFooter() {
  return (
    <footer className="ui-footer">
      <div className="ui-container ui-footer-inner">
        <BrandLogo />
        <span className="ui-footer-copy">
          © {new Date().getFullYear()} <BrandName />. All rights reserved.
        </span>
        <nav className="ui-footer-links">
          <Link href="/pricing">Pricing</Link>
          <Link href="/privacy-policy">Privacy Policy</Link>
          <Link href="/terms">Terms of Service</Link>
          <Link href="/refund-policy">Refund Policy</Link>
          <Link href="/contact">Contact</Link>
        </nav>
      </div>
    </footer>
  )
}
