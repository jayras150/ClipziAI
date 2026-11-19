// Manifest PWA dinamis: ikon mengikuti favicon yang diunggah admin
// (slot icon192/icon512/maskable512), jadi home screen Android/iOS otomatis
// memakai ikon terbaru tanpa rebuild frontend.
import type { NextRequest } from "next/server"

export const dynamic = "force-dynamic"

type BrandingPayload = {
  app_name?: string
  tagline?: string | null
  accent_color?: string | null
  favicon_url?: string | null
  favicons?: Record<string, string | null> | null
  version?: string | null
}

async function loadBranding(): Promise<BrandingPayload | null> {
  const base =
    process.env.API_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://backend:8000"
  try {
    const response = await fetch(base.replace(/\/$/, "") + "/api/branding", {
      cache: "no-store",
      signal: AbortSignal.timeout(4000)
    })
    if (!response.ok) return null
    return (await response.json()) as BrandingPayload
  } catch {
    return null
  }
}

export async function GET(_request: NextRequest) {
  const branding = await loadBranding()
  const name = branding?.app_name || "Clipzy AI"
  const favicons = branding?.favicons || {}
  const version = branding?.version || ""
  const withV = (url?: string | null) => {
    if (!url) return undefined
    if (!version) return url
    return url.includes("?") ? `${url}&v=${version}` : `${url}?v=${version}`
  }

  const icon192 = withV(favicons.icon192 || favicons.icon32 || branding?.favicon_url)
  const icon512 = withV(favicons.icon512 || favicons.icon32 || branding?.favicon_url)
  const maskable = withV(favicons.maskable512) || icon512

  const icons: Array<Record<string, string>> = []
  if (icon192) icons.push({ src: icon192, sizes: "192x192", type: "image/png", purpose: "any" })
  if (icon512) icons.push({ src: icon512, sizes: "512x512", type: "image/png", purpose: "any" })
  if (maskable) {
    icons.push({ src: maskable, sizes: "512x512", type: "image/png", purpose: "maskable" })
  }

  const manifest = {
    name,
    short_name: name.slice(0, 12),
    description: branding?.tagline || "Turn long videos into viral shorts",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    background_color: "#0b0d12",
    theme_color: branding?.accent_color || "#f4c76b",
    icons
  }

  return new Response(JSON.stringify(manifest), {
    status: 200,
    headers: {
      "Content-Type": "application/manifest+json; charset=utf-8",
      "Cache-Control": "no-store, max-age=0"
    }
  })
}
