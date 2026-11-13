/** @type {import('next').NextConfig} */
const ADMIN_URL = process.env.ADMIN_URL || "https://admin.proxyai.live"

const nextConfig = {
  reactStrictMode: true,
  // Saat dibuild di Docker (ENV DOCKER_BUILD=1) pakai output standalone agar
  // image runtime hanya membawa file yang dibutuhkan.
  ...(process.env.DOCKER_BUILD === "1" ? { output: "standalone" } : {}),
  // Panel admin hanya ada di subdomain admin.*; rute lama di domain publik
  // dialihkan supaya bookmark lama tidak berakhir 404.
  async redirects() {
    return [
      { source: "/admin", destination: ADMIN_URL, permanent: true },
      { source: "/admin/:path*", destination: `${ADMIN_URL}/:path*`, permanent: true },
    ]
  },
}

module.exports = nextConfig
