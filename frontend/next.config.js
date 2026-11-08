/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Saat dibuild di Docker (ENV DOCKER_BUILD=1) pakai output standalone agar
  // image runtime hanya membawa file yang dibutuhkan.
  ...(process.env.DOCKER_BUILD === "1" ? { output: "standalone" } : {}),
}

module.exports = nextConfig