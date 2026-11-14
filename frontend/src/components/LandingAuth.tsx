"use client"

import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { useEffect, useState } from "react"

import UserMenu from "@/components/UserMenu"
import { AUTH_EVENT, hasSession } from "@/lib/auth"

/**
 * Aksi navbar untuk halaman marketing.
 *
 * Sebelumnya landing page menulis "Sign in" secara statis, sehingga pengguna
 * yang sudah login tetap melihat tombol login saat pindah ke Features/Demo
 * (anchor di halaman ini) — terlihat seperti sesinya hilang. Komponen ini
 * membaca sesi dan ikut berubah saat tab lain login/logout.
 */
export default function LandingAuth() {
  const [signedIn, setSignedIn] = useState(false)

  useEffect(() => {
    const sync = () => setSignedIn(hasSession())
    sync()
    window.addEventListener("storage", sync)
    window.addEventListener(AUTH_EVENT, sync)
    return () => {
      window.removeEventListener("storage", sync)
      window.removeEventListener(AUTH_EVENT, sync)
    }
  }, [])

  if (signedIn) return <UserMenu />

  return (
    <>
      <Link className="btn btn-ghost" href="/login">
        Sign in
      </Link>
      <Link className="btn btn-gold" href="/register">
        Start free <ArrowRight size={16} />
      </Link>
    </>
  )
}
