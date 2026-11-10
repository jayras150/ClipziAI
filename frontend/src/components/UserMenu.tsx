"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { CreditCard, LayoutDashboard, LogOut, ShieldCheck, UserRound } from "lucide-react"

import { api, UserProfileData } from "@/lib/api"
import { AUTH_EVENT, clearSession, hasSession } from "@/lib/auth"

/** Inisial untuk avatar: "Alex Carter" -> "AC", fallback ke huruf pertama email. */
function initials(name?: string | null, email?: string | null): string {
  const trimmed = (name || "").trim()
  if (trimmed) {
    return trimmed
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part.charAt(0))
      .join("")
      .toUpperCase()
  }
  return (email || "?").charAt(0).toUpperCase()
}

/**
 * Avatar + dropdown card akun.
 *
 * Data profil dibaca di useEffect (bukan saat render) supaya tidak ada
 * hydration mismatch — token tersimpan di localStorage yang tidak ada di server.
 */
export default function UserMenu() {
  const [open, setOpen] = useState(false)
  const [profile, setProfile] = useState<UserProfileData | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  const loadProfile = useCallback(() => {
    const token = window.localStorage.getItem("token")
    if (!token) {
      setProfile(null)
      return
    }
    api
      .getProfile(token)
      .then(setProfile)
      .catch(() => {
        /* biarkan avatar menampilkan inisial default */
      })
  }, [])

  useEffect(() => {
    loadProfile()
    const sync = () => {
      if (!hasSession()) setProfile(null)
      else loadProfile()
    }
    window.addEventListener("storage", sync)
    window.addEventListener(AUTH_EVENT, sync)
    return () => {
      window.removeEventListener("storage", sync)
      window.removeEventListener(AUTH_EVENT, sync)
    }
  }, [loadProfile])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onPointerDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onPointerDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  const signOut = () => {
    clearSession()
    window.location.href = "/login"
  }

  return (
    <div className="ui-menu" ref={boxRef}>
      <button
        type="button"
        className="ui-avatar"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        title={profile?.name || profile?.email || "Account"}
      >
        {initials(profile?.name, profile?.email)}
      </button>

      {open && (
        <div className="ui-dropdown" role="menu">
          <div className="ui-dropdown-head">
            <span className="ui-dropdown-name">{profile?.name || "Your account"}</span>
            {profile?.email && <span className="ui-dropdown-mail">{profile.email}</span>}
            {profile && (
              <span className="ui-dropdown-credit">
                {profile.credits_balance} credits · {profile.plan_type} plan
              </span>
            )}
          </div>
          <Link className="ui-dropdown-item" href="/profile" role="menuitem" onClick={() => setOpen(false)}>
            <UserRound size={15} /> My Profile
          </Link>
          {profile?.is_admin && (
            <Link className="ui-dropdown-item" href="/admin" role="menuitem" onClick={() => setOpen(false)}>
              <ShieldCheck size={15} /> Admin panel
            </Link>
          )}
          <Link className="ui-dropdown-item" href="/dashboard" role="menuitem" onClick={() => setOpen(false)}>
            <LayoutDashboard size={15} /> Dashboard
          </Link>
          <Link className="ui-dropdown-item" href="/pricing" role="menuitem" onClick={() => setOpen(false)}>
            <CreditCard size={15} /> Pricing
          </Link>
          <button type="button" className="ui-dropdown-item danger" role="menuitem" onClick={signOut}>
            <LogOut size={15} /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}
