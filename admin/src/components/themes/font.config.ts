/**
 * Font memakai stack sistem (Tailwind `font-sans`), BUKAN `next/font/google`.
 *
 * Alasan: `next/font/google` mengunduh font SAAT BUILD. Di server tanpa akses
 * fonts.googleapis.com build gagal ("Failed to fetch Space Mono from Google
 * Fonts"). Frontend publik ClipzyAI memakai pendekatan yang sama.
 */
export const fontVariables = '';
