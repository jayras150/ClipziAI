"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { CreditCard, LayoutDashboard, LogOut, Unlink, Youtube } from "lucide-react"

import { api, UserProfileData } from "@/lib/api"
import { AUTH_EVENT, clearSession, hasSession } from "@/lib/auth"

/** Ikon profil (SVG yang diminta): kepala + bahu, mengikuti gaya Lucide. */
function ProfileIcon({ size = 15 }: { size?: number }) {
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
        <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </g>
    </svg>
  )
}

/**
 * Avatar + dropdown card akun.
 *
 * Data profil dibaca di useEffect (bukan saat render) supaya tidak ada
 * hydration mismatch — token tersimpan di localStorage yang tidak ada di server.
 */
export default function UserMenu({
  youtube,
  onConnectYouTube,
  onDisconnectYouTube,
}: {
  /** Info YouTube untuk menu mobile (tombol connect/disconnect pindah ke sini). */
  youtube?: { connected: boolean; channelName?: string; loading?: boolean }
  onConnectYouTube?: () => void
  onDisconnectYouTube?: () => void
} = {}) {
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
        <ProfileIcon size={18} />
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
            <ProfileIcon size={15} /> My Profile
          </Link>
          <Link className="ui-dropdown-item" href="/dashboard" role="menuitem" onClick={() => setOpen(false)}>
            <LayoutDashboard size={15} /> Dashboard
          </Link>
          <Link className="ui-dropdown-item" href="/pricing" role="menuitem" onClick={() => setOpen(false)}>
            <CreditCard size={15} /> Pricing
          </Link>
          {youtube && (
            <>
              <div className="ui-dropdown-sep ui-only-mobile" />
              {youtube.connected ? (
                <>
                  <div className="ui-dropdown-note ui-only-mobile">
                    YouTube · {youtube.channelName || "connected"}
                  </div>
                  <button
                    type="button"
                    className="ui-dropdown-item danger ui-only-mobile"
                    role="menuitem"
                    disabled={youtube.loading || !onDisconnectYouTube}
                    onClick={() => {
                      setOpen(false)
                      onDisconnectYouTube?.()
                    }}
                  >
                    <Unlink size={15} /> Disconnect YouTube
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="ui-dropdown-item ui-only-mobile"
                  role="menuitem"
                  disabled={youtube.loading || !onConnectYouTube}
                  onClick={() => {
                    setOpen(false)
                    onConnectYouTube?.()
                  }}
                >
                  <Youtube size={15} className="yt-icon" fill="#ff2d2d" strokeWidth={0} /> Connect YouTube
                </button>
              )}
            </>
          )}
          <button type="button" className="ui-dropdown-item danger" role="menuitem" onClick={signOut}>
            <LogOut size={15} /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}
