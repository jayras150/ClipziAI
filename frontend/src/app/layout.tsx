// Root layout (App Router).
// NEXT_PUBLIC_API_URL dibaca saat runtime oleh klien melalui /runtime-env.js
// yang ditulis oleh frontend/docker-entrypoint.sh ketika container start.
import type { Metadata } from "next"
import Script from "next/script"
import { BrandingProvider, type Branding } from "@/components/BrandingProvider"
import "./globals.css"
import "./theme.css"
import "./landing.css"

// Font dimuat lewat <link> ke Google Fonts (runtime), BUKAN next/font/google.
// next/font/google mengunduh CSS font SAAT BUILD, sehingga build di server yang
// koneksinya ke fonts.googleapis.com tidak stabil gagal dengan
// "An error occurred in `next/font`". Dengan <link> build jadi deterministik,
// dan CSS tetap punya fallback system-ui bila CDN tidak bisa diakses.
const GOOGLE_FONTS_HREF =
  "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap"

type BrandingData = Branding & {
  app_name?: string
  tagline?: string | null
  favicon_url?: string | null
}

// Branding diambil dari API (diatur admin). Server-side fetch supaya favicon dan
// judul halaman ikut berubah tanpa rebuild frontend.
async function loadBranding(): Promise<BrandingData | null> {
  // Nama service di docker compose adalah `backend` (container clipzi-api).
  // API_INTERNAL_URL diisi compose; fallback ini hanya jaring pengaman.
  const base =
    process.env.API_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://backend:8000"
  try {
    // Timeout pendek: branding TIDAK boleh menahan render/healthcheck bila API
    // sedang lambat atau mati. Gagal -> pakai default.
    const response = await fetch(base.replace(/\/$/, "") + "/api/branding", {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    })
    if (!response.ok) return null
    return (await response.json()) as BrandingData
  } catch {
    return null
  }
}

export async function generateMetadata(): Promise<Metadata> {
  const branding = await loadBranding()
  const name = branding?.app_name || "Clipzy AI"
  const description =
    branding?.tagline ||
    "Clipzy AI turns long videos into short, ready-to-publish clips with AI highlight detection, subtitles, and vertical reframing."
  const rawIcon = branding?.favicon_url || undefined
  const version = branding?.version || undefined
  // ?v=<hash> memaksa browser memuat favicon baru setelah admin mengganti logo.
  const icon =
    rawIcon && version
      ? rawIcon.includes("?")
        ? `${rawIcon}&v=${version}`
        : `${rawIcon}?v=${version}`
      : rawIcon
  return {
    title: name + " - Create More. Edit Less.",
    description,
    icons: icon ? { icon, shortcut: icon, apple: icon } : undefined,
    openGraph: branding?.og_image_url
      ? { title: name, description, images: [branding.og_image_url] }
      : { title: name, description },
  }
}


export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Branding dipakai SEMUA halaman (header landing, login, register, dashboard,
  // footer) lewat context, bukan hardcode per file.
  const branding = await loadBranding()
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href={GOOGLE_FONTS_HREF} />
      </head>
      <body>
        {/* Konfigurasi runtime (NEXT_PUBLIC_API_URL) dimuat sebelum bundle klien */}
        <Script src="/runtime-env.js" strategy="beforeInteractive" />
        <BrandingProvider initial={branding}>{children}</BrandingProvider>
      </body>
    </html>
  )
}
