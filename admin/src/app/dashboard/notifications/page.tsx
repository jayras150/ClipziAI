import PageContainer from '@/components/layout/page-container';
import { adminFetch } from '@/lib/clipzi';
import { AlertsList, type AlertItem } from '@/features/notifications/components/alerts-list';

export const metadata = { title: 'Admin: Alerts' };
export const dynamic = 'force-dynamic';

/**
 * Halaman Alerts.
 *
 * Memakai sumber yang SAMA dengan lonceng header (`/api/admin/notifications`):
 * task gagal, worker error (termasuk log tersimpan), runner, security event,
 * dan env Vast. Setiap baris punya tombol "Detail / Cek Log" yang menampilkan
 * pesan lengkap + potongan log.
 */
export default async function AlertsPage() {
  let items: AlertItem[] = [];
  let error = '';

  try {
    const data = await adminFetch<{ items: AlertItem[]; unread_count: number }>(
      '/api/admin/notifications'
    );
    items = data.items || [];
  } catch (err) {
    error = err instanceof Error ? err.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat alert.';
  }

  const unread = items.filter((item) => !item.read).length;

  return (
    <PageContainer
      pageTitle='Alerts'
      pageDescription={`${items.length} alert aktif · ${unread} belum dibaca — sumber sama dengan lonceng header`}
    >
      <div className='space-y-4'>
        {error ? (
          <p className='text-destructive border-destructive/40 bg-destructive/10 rounded-md border px-3 py-2 text-sm'>
            {error}
          </p>
        ) : null}
        <AlertsList items={items} />
      </div>
    </PageContainer>
  );
}
