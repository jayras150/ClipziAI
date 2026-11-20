import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // ID build: dipakai Next untuk mendeteksi klien yang memakai bundle lama
  // setelah deploy. Tanpa ini, tab lama mengirim Server Action ID yang sudah
  // tidak ada -> "Failed to find Server Action" -> React #441.
  deploymentId: process.env.NEXT_DEPLOYMENT_ID || undefined,
  output: process.env.BUILD_STANDALONE === 'true' ? 'standalone' : undefined,
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'api.slingacademy.com',
        port: ''
      }
    ]
  },
  experimental: {
    // Upload branding (logo/OG/favicon & video hero landing) dikirim lewat
    // Server Action. Batas bawaan Next hanya 1 MB, sehingga video hero > 1 MB
    // selalu gagal dengan `Body exceeded 1 MB limit` (413) dan tidak pernah
    // sampai ke backend. Backend sendiri mengizinkan video sampai 30 MB.
    serverActions: {
      bodySizeLimit: '32mb'
    },
    // Next 16 menyalin body request ke memori saat `proxy.ts` aktif; batas
    // bawaan 10 MB sehingga body video 30 MB terpotong jadi peringatan.
    proxyClientMaxBodySize: '32mb'
  },
  transpilePackages: ['geist'],
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production'
  }
};

export default nextConfig;
