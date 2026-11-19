'use client';

import { useEffect } from 'react';

/**
 * Pemantau versi build admin.
 *
 * Tab admin yang dibiarkan terbuka setelah deploy memakai bundle lama; Server
 * Action ID-nya sudah tidak ada di server → "Failed to find Server Action"
 * (React #441). Watcher ini membandingkan /api/version tiap 60 detik dan
 * memuat ulang halaman saat build berubah, sehingga tombol tetap berfungsi.
 */
export function VersionWatcher({ intervalMs = 60000 }: { intervalMs?: number }) {
  useEffect(() => {
    let current = '';
    let stopped = false;

    const check = async () => {
      try {
        const response = await fetch('/api/version', { cache: 'no-store' });
        if (!response.ok || stopped) return;
        const data = (await response.json()) as { id?: string };
        const id = String(data?.id || '');
        if (!id) return;
        if (!current) {
          current = id;
          return;
        }
        if (id !== current) {
          stopped = true;
          window.location.reload();
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
  }, [intervalMs]);

  return null;
}
