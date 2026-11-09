// Tipe global aplikasi.
//
// File ini adalah MODULE (karena memakai `export {}`), jadi deklarasi wildcard
// untuk aset (*.css, *.svg, dst.) TIDAK boleh ditaruh di sini — lihat
// `src/types/assets.d.ts` yang sengaja script-mode.

export {};

declare global {
  interface Window {
    /**
     * Konfigurasi runtime yang ditulis oleh docker-entrypoint.sh ke
     * /app/public/runtime-env.js saat container start.
     */
    __ENV__?: {
      NEXT_PUBLIC_API_URL?: string;
      NEXT_PUBLIC_GOOGLE_CLIENT_ID?: string;
    };
  }
}
