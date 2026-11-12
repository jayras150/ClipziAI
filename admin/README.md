# ClipzyAI Admin

Aplikasi admin ClipzyAI, dibangun dari template
[Kiranism/next-shadcn-dashboard-starter](https://github.com/Kiranism/next-shadcn-dashboard-starter)
(MIT) dengan Clerk dan halaman demo sudah dicabut lewat `scripts/cleanup.js`.

## Menjalankan

```bash
npm install
cp .env.example .env.local     # isi CLIPZI_API_URL
npm run dev                    # http://localhost:3000/auth/sign-in
```

`CLIPZI_API_URL` harus mengarah ke backend ClipzyAI:

- lokal: `http://127.0.0.1:8000`
- docker compose: `http://clipzi-api:8000`

## Autentikasi

- Login memakai endpoint backend `POST /api/auth/login`, lalu dicek ke
  `GET /api/admin/auth/me`. Token disimpan di cookie HttpOnly
  `clipzi_admin_token` (12 jam).
- `src/proxy.ts` mengalihkan semua halaman (kecuali `/auth/*`) ke
  `/auth/sign-in` bila cookie tidak ada.
- Semua request ke API dilakukan di server (`src/lib/clipzi.ts`) dengan header
  `Authorization: Bearer <token>` dari cookie tersebut.

## Halaman yang sudah terpasang

| Route | Isi |
|---|---|
| `/auth/sign-in` | Login admin |
| `/dashboard/overview` | Shell dashboard (dari template) |
| `/dashboard/settings/ai` | Provider, base URL, API key, model, temperature, token, timeout, toggle, Test Connection |
| `/dashboard/settings/branding` | Nama app, tagline, warna aksen, logo, favicon |

Modul berikut (tasks, users, workers, transactions, audit, plans, system,
notifications) menyusul memakai pola data-table/form template.

## Build produksi

```bash
BUILD_STANDALONE=true npm run build
node .next/standalone/server.js
```

Docker: `docker build -t sujinwo555/clipzi-admin .` (Dockerfile memakai npm, bukan bun).
