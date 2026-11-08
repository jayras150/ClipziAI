import type { Metadata } from "next"
import { Inter } from "next/font/google"
import Script from "next/script"
import "./globals.css"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "Clipzi AI - Turn Long Videos into Viral Shorts",
  description: "Clipzi AI automatically transcribes, detects viral hooks, frames speakers in 9:16, and burns animated captions in seconds.",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="id">
      <body className={inter.className}>
        {/* Konfigurasi runtime (NEXT_PUBLIC_API_URL) dimuat sebelum bundle klien */}
        <Script src="/runtime-env.js" strategy="beforeInteractive" />
        {children}
      </body>
    </html>
  )
}