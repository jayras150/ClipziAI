// Root layout (App Router).
// NEXT_PUBLIC_API_URL dibaca saat runtime oleh klien melalui /runtime-env.js
// yang ditulis oleh frontend/docker-entrypoint.sh ketika container start.
import type { Metadata } from "next"
import Script from "next/script"
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

export const metadata: Metadata = {
  title: "Clipzy AI — Create More. Edit Less.",
  description:
    "Clipzy AI turns long videos into short, ready-to-publish clips with AI highlight detection, subtitles, and vertical reframing.",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
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
        {children}
      </body>
    </html>
  )
}
