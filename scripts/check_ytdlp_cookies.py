#!/usr/bin/env python3
"""
Health check & rotasi otomatis cookies yt-dlp.

Jalankan berkala (cron / Vast.ai startup script / sidecar container):

    # tiap 6 jam
    0 */6 * * * cd /app/backend && python ../scripts/check_ytdlp_cookies.py >> /var/log/clipzi-cookies.log 2>&1

Apa yang dilakukan:
  1. Probe setiap cookies berstatus `active` memakai video uji.
  2. Bila gagal / pesan error menandakan sesi mati -> status jadi `expired`.
  3. Bila yt-dlp sudah merotasi token -> ciphertext di DB diperbarui.
  4. Print ringkasan; exit code 1 bila ada cookies yang jadi expired
     (berguna untuk alerting).

Butuh tabel ytdlp_cookies -> jalankan backend sekali agar init_db() membuatnya.
"""
import asyncio
import os
import sys
from pathlib import Path

# Pastikan import `app.*` berjalan dari folder backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if BACKEND_DIR.exists():
    sys.path.insert(0, str(BACKEND_DIR))
    os.chdir(BACKEND_DIR)


async def main() -> int:
    from app.db.session import AsyncSessionLocal
    from app.services import cookie_store

    async with AsyncSessionLocal() as db:
        cookies = await cookie_store.list_cookies(db)
        if not cookies:
            print("[cookies] Tidak ada cookies tersimpan (download akan tanpa cookies).")
            return 0

        print(f"[cookies] Total: {len(cookies)}")
        results = await cookie_store.probe_all(db)

        if not results:
            print("[cookies] Tidak ada cookies berstatus active untuk diuji.")
            return 0

        newly_expired = 0
        for item in results:
            mark = "OK   " if item["ok"] else "GAGAL"
            print(f"  {mark} {item['label']:<20} status={item['status']}")
            if not item["ok"]:
                err = (item["error"] or "").strip().replace("\n", " ")[:160]
                print(f"          -> {err}")
                if item["status"] == "expired":
                    newly_expired += 1

        if newly_expired:
            print(
                f"\n[cookies] PERHATIAN: {newly_expired} cookies expired. "
                "Upload cookies baru lewat POST /api/admin/ytdlp-cookies"
            )
            return 1

        print("\n[cookies] Semua cookies aktif masih valid.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
