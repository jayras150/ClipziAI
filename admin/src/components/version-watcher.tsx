'use client';

import { useEffect } from 'react';

/**
 * Pemantau versi build admin.
 *
 * Tab admin yang dibiarkan terbuka setelah deploy memakai bundle lama; Server
 * Action ID-nya sudah tidak ada di server → "Failed to find Server Action"
 * (React #441) dan SEMUA aksi (termasuk unggah video hero / simpan branding)
 * gagal tanpa menyentuh backend.
 *
 * Versi lama watcher menyimpan ID hasil fetch pertama sebagai pembanding,
 * sehingga tab yang dibuka SEBELUM deploy tidak pernah tahu bahwa dirinya
 * basi (`current` = ID server yang baru, tidak ada perubahan berikutnya) —
 * persis kondisi "sudah unggah tapi tidak tersimpan".
 *
 * Sekarang pembandingnya adalah `buildId` milik halaman ini (di-render server
 * dari NEXT_DEPLOYMENT_ID): bila berbeda dengan /api/version, halaman langsung
 * dimuat ulang sekali (guard 30 detik untuk mencegah loop).
 */
const RELOAD_GUARD_MS = 30_000;
const RELOAD_GUARD_KEY = 'clipzi_version_reload_at';

function reloadOnce(): void {
  try {
    const last = Number(window.sessionStorage.getItem(RELOAD_GUARD_KEY) || 0);
    if (Date.now() - last < RELOAD_GUARD_MS) return;
    window.sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()));
  } catch {
    /* sessionStorage diblokir: tetap reload, loop dicegah oleh jarak fetch */
  }
  window.location.reload();
}

export function VersionWatcher({
  buildId = '',
  intervalMs = 60000
}: {
  /** ID build halaman ini (dari NEXT_DEPLOYMENT_ID saat render server). */
  buildId?: string;
  intervalMs?: number;
}) {
  useEffect(() => {
    let stopped = false;
    let current = '';

    const check = async () => {
      try {
        const response = await fetch('/api/version', { cache: 'no-store' });
        if (!response.ok || stopped) return;
        const data = (await response.json()) as { id?: string };
        const id = String(data?.id || '');
        if (!id) return;

        // Tab basi: bundle halaman ini beda dengan build yang sedang aktif.
        if (buildId && buildId !== 'dev' && id !== buildId) {
          stopped = true;
          reloadOnce();
          return;
        }

        // Jaring pengaman untuk build yang tidak punya ID (mis. dev): deteksi
        // perubahan antar pengecekan seperti perilaku lama.
        if (!current) {
          current = id;
          return;
        }
        if (id !== current) {
          stopped = true;
          reloadOnce();
        }
      } catch {
        /* offline sesaat: abaikan */
      }
    };

    void check();
    const timer = window.setInterval(() => void check(), Math.max(15000, intervalMs));
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [buildId, intervalMs]);

  return null;
}
