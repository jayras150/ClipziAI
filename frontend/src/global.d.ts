// Deklarasi tipe untuk side-effect import CSS global (mis. `import "./globals.css"`).
// Next.js/types hanya mendeklarasikan `*.module.css`, sehingga tanpa deklarasi ini
// TypeScript alias editor melaporkan error ts(2882).
declare module "*.css";

export {};

declare global {
  interface Window {
    /**
     * Konfigurasi runtime yang ditulis oleh docker-entrypoint.sh ke
     * /app/public/runtime-env.js saat container start.
     */
    __ENV__?: {
      NEXT_PUBLIC_API_URL?: string;
    };
  }
}
