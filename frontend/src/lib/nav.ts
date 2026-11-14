/**
 * Tautan navigasi aplikasi (dipakai navbar desktop & drawer mobile).
 * Satu sumber supaya tidak ada menu yang hilang di halaman mana pun.
 */
export const APP_NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/#features", label: "Features" },
  { href: "/#how", label: "How it works" },
  { href: "/#demo", label: "Demo" },
  { href: "/pricing", label: "Pricing" },
  { href: "/contact", label: "Contact" },
] as const
