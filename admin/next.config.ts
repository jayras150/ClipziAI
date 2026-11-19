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
  transpilePackages: ['geist'],
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production'
  }
};

export default nextConfig;
