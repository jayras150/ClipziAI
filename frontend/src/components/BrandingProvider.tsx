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
  /** Favicon per device: icon32 | icon192 | icon512 | apple180 | maskable512 | ico | svg */
  favicons?: Record<string, string | null> | null
  og_image_url?: string | null
  hero_video_url?: string | null
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
  hero_video_url: null,
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

// Cache modul (stale-while-revalidate) supaya branding tidak kembali ke default
// hanya karena API sesaat lambat saat refresh halaman.
let cachedBranding: Branding | null = null
let cachedAt = 0
const BRANDING_TTL = 60_000 // 60 detik

async function fetchBrandingWithRetry(): Promise<Branding | null> {
  const base = getApiBaseUrl()
  let lastError: unknown = null
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 8000)
      const response = await fetch(`${base}/api/branding`, {
        cache: "no-store",
        signal: controller.signal,
      })
      clearTimeout(timeoutId)
      if (response.ok) {
        const data = (await response.json()) as Branding
        return normalize(data)
      }
      lastError = new Error(`HTTP ${response.status}`)
    } catch (error) {
      lastError = error
      // Tunda singkat sebelum coba lagi
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  }
  // Jika gagal, pakai cache bila masih dalam TTL.
  if (cachedBranding && Date.now() - cachedAt < BRANDING_TTL) {
    return cachedBranding
  }
  console.warn('[Branding] Gagal memuat branding:', lastError)
  return null
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
      const data = await fetchBrandingWithRetry()
      if (data) {
        cachedBranding = data
        cachedAt = Date.now()
        setBranding(data)
      }
    } catch {
      /* biarkan branding lama; jangan ganggu UI */
    }
  }, [])

  // Saat mounting: pakai cache jika ada, lalu fetch di background.
  useEffect(() => {
    if (cachedBranding && Date.now() - cachedAt < BRANDING_TTL) {
      setBranding(cachedBranding)
    }
    void refresh()
  }, [refresh])

  // Warna aksen ikut berubah tanpa reload.
  useEffect(() => {
    const accent = branding.accent_color || DEFAULT_BRANDING.accent_color
    document.documentElement.style.setProperty("--ui-gold", accent as string)
  }, [branding.accent_color])

  // Judul tab + semua ikon (favicon multi-device) ikut branding.
  useEffect(() => {
    const suffix = "Create More. Edit Less."
    document.title = branding.app_name ? `${branding.app_name} - ${suffix}` : suffix

    const favicons = branding.favicons || {}
    const base = favicons.icon32 || branding.favicon_url

    const upsert = (rel: string, url?: string | null, sizes?: string, type?: string) => {
      if (!url) return
      const href = withVersion(url, branding.version)
      if (!href) return
      const key = `clipzyIcon${rel}${sizes || ""}`
      let link = document.head.querySelector<HTMLLinkElement>(`link[data-${key}]`)
      if (!link) {
        link = document.createElement("link")
        link.rel = rel
        if (sizes) link.sizes = sizes
        if (type) link.type = type
        link.dataset[key] = "1"
        document.head.appendChild(link)
      }
      link.href = href
    }

    upsert("icon", favicons.ico, "any", "image/x-icon")
    upsert("icon", favicons.svg, "any", "image/svg+xml")
    upsert("icon", favicons.icon32 || base, "32x32", "image/png")
    upsert("icon", favicons.icon192, "192x192", "image/png")
    upsert("icon", favicons.icon512, "512x512", "image/png")
    upsert("apple-touch-icon", favicons.apple180 || base, "180x180", "image/png")
    upsert("masked-icon", favicons.maskable512, "512x512", "image/png")
  }, [
    branding.app_name,
    branding.favicon_url,
    branding.favicons,
    branding.version
  ])

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
          width={variant === "landing" ? 132 : 140}
          height={variant === "landing" ? 28 : 30}
          loading="eager"
          decoding="sync"
          onError={(e) => {
            const el = e.currentTarget
            el.style.display = 'none'
          }}
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
    return (
      // eslint-disable-next-line @next/next/no-img-element
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
