// Root layout (App Router).
// NEXT_PUBLIC_API_URL dibaca saat runtime oleh klien melalui /runtime-env.js
// yang ditulis oleh frontend/docker-entrypoint.sh ketika container start.
import type { Metadata } from "next"
import { DM_Sans, Space_Grotesk } from "next/font/google"
import Script from "next/script"
import "./globals.css"
import "./landing.css"

// Font landing page (desain: DM Sans untuk teks, Space Grotesk untuk judul).
// Diekspos sebagai CSS variable agar bisa dipakai di landing.css.
const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-dm",
  display: "swap",
})

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-space",
  display: "swap",
})

export const metadata: Metadata = {
  title: "Clipzy AI — Create More. Edit Less.",
  description:
    "Clipzy AI — Ubah video panjang menjadi konten pendek yang siap viral dengan bantuan AI.",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="id" className={`${dmSans.variable} ${spaceGrotesk.variable}`}>
      <body className={dmSans.className}>
        {/* Konfigurasi runtime (NEXT_PUBLIC_API_URL) dimuat sebelum bundle klien */}
        <Script src="/runtime-env.js" strategy="beforeInteractive" />
        {children}
      </body>
    </html>
  )
}
