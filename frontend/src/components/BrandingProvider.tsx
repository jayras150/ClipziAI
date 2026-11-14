"use client"

/**
 * Branding runtime untuk frontend.
 *
 * Masalah lama: hanya Navbar yang memakai branding; header landing, login,
 * register, dashboard, dan footer masih hardcode "▶ Clipzy AI" sehingga
 * perubahan logo/nama dari admin tidak terlihat di semua halaman.
 *
 * Sekarang semua komponen memakai `<BrandLogo />` / `useBranding()` yang
 * sumbernya satu: `/api/branding` (server-side initial + refresh client).
 */
import Link from "next/link"
import { Play } from "lucide-react"
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"

import { getApiBaseUrl } from "@/lib/env"

export type Branding = {
  app_name: string
  tagline?: string | null
  logo_url?: string | null
  favicon_url?: string | null
  og_image_url?: string | null
  accent_color?: string | null
  support_email?: string | null
  footer_note?: string | null
  version?: string | null
}

export const DEFAULT_BRANDING: Branding = {
  app_name: "Clipzy AI",
  tagline: "Turn long videos into viral shorts",
  logo_url: null,
  favicon_url: null,
  og_image_url: null,
  accent_color: "#f4c76b",
  support_email: null,
  footer_note: null,
  version: null,
}

type BrandingContextValue = {
  branding: Branding
  refresh: () => Promise<void>
}

const BrandingContext = createContext<BrandingContextValue>({
  branding: DEFAULT_BRANDING,
  refresh: async () => undefined,
})

function normalize(value: Branding | null | undefined): Branding {
  return { ...DEFAULT_BRANDING, ...(value || {}) }
}

function withVersion(url?: string | null, version?: string | null): string | undefined {
  if (!url) return undefined
  if (!version) return url
  return url.includes("?") ? `${url}&v=${version}` : `${url}?v=${version}`
}

export function BrandingProvider({
  initial,
  children,
}: {
  initial?: Branding | null
  children: React.ReactNode
}) {
  const [branding, setBranding] = useState<Branding>(() => normalize(initial))

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(getApiBaseUrl() + "/api/branding", { cache: "no-store" })
      if (response.ok) setBranding(normalize((await response.json()) as Branding))
    } catch {
      /* biarkan branding lama; jangan ganggu UI */
    }
  }, [])

  // Warna aksen ikut berubah tanpa reload.
  useEffect(() => {
    const accent = branding.accent_color || DEFAULT_BRANDING.accent_color
    document.documentElement.style.setProperty("--ui-gold", accent as string)
  }, [branding.accent_color])

  // Judul tab + favicon ikut branding (tab yang sedang terbuka).
  useEffect(() => {
    const suffix = "Create More. Edit Less."
    document.title = branding.app_name ? `${branding.app_name} - ${suffix}` : suffix

    const icon = withVersion(branding.favicon_url, branding.version)
    if (!icon) return
    let link = document.querySelector<HTMLLinkElement>("link[data-clipzy-favicon]")
    if (!link) {
      link = document.createElement("link")
      link.rel = "icon"
      link.dataset.clipzyFavicon = "1"
      document.head.appendChild(link)
    }
    link.href = icon
  }, [branding.app_name, branding.favicon_url, branding.version])

  const value = useMemo(() => ({ branding, refresh }), [branding, refresh])
  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>
}

export function useBranding(): BrandingContextValue {
  return useContext(BrandingContext)
}

/**
 * Logo + nama brand. `variant="ui"` untuk halaman app (class `ui-brand`),
 * `variant="landing"` untuk header landing (class `brand`).
 */
export function BrandLogo({
  variant = "ui",
  showName = true,
  href = "/",
  onClick,
  className = "",
}: {
  variant?: "ui" | "landing"
  showName?: boolean
  href?: string
  onClick?: () => void
  className?: string
}) {
  const { branding } = useBranding()
  const name = branding.app_name || DEFAULT_BRANDING.app_name
  const logo = withVersion(branding.logo_url, branding.version)

  const brandClass = variant === "landing" ? "brand" : "ui-brand"
  const markClass = variant === "landing" ? "brand-mark" : "ui-brand-mark"
  // Bila logo gambar sudah diunggah, header hanya menampilkan gambar (tanpa teks
  // nama) supaya tidak dobel/turang rapi. Tanpa logo, tetap ada mark + nama.
  const withName = showName && !logo

  return (
    <Link
      className={`${brandClass} ${logo ? "brand-has-image" : ""} ${className}`.trim()}
      href={href}
      onClick={onClick}
    >
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className={variant === "landing" ? "brand-logo-img" : "ui-brand-logo"}
          src={logo}
          alt={name}
        />
      ) : (
        <span className={markClass}>
          <Play size={16} fill="currentColor" strokeWidth={0} />
        </span>
      )}
      {withName ? <span>{name}</span> : null}
    </Link>
  )
}

/** Nama aplikasi saja (untuk heading/footer). */
export function BrandName() {
  const { branding } = useBranding()
  return <>{branding.app_name || DEFAULT_BRANDING.app_name}</>
}

/** Mark saja (dipakai di kartu login/register). */
export function BrandMark({ size = 32 }: { size?: number }) {
  const { branding } = useBranding()
  const logo = withVersion(branding.logo_url, branding.version)
  if (logo) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={logo}
        alt={branding.app_name || "logo"}
        style={{ width: size, height: size, objectFit: "contain", borderRadius: 10 }}
      />
    )
  }
  return (
    <span
      className="ui-brand-mark"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
    >
      <Play size={Math.round(size * 0.45)} fill="currentColor" strokeWidth={0} />
    </span>
  )
}
