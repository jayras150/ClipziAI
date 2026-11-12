import PageContainer from '@/components/layout/page-container';
import TableShell, { type Column } from '@/features/admin/table-shell';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Plans' };

const columns: Column[] = [
  { key: 'id', label: 'ID' },
  { key: 'name', label: 'Nama' },
  {
    key: 'price_monthly',
    label: 'Harga/bulan',
    render: (row) => 'Rp ' + Number(row.price_monthly ?? 0).toLocaleString('id-ID')
  },
  { key: 'credits_monthly', label: 'Kredit' },
  { key: 'max_video_duration_minutes', label: 'Durasi maks (menit)' },
  { key: 'max_concurrent_tasks', label: 'Task paralel' },
  { key: 'watermark', label: 'Watermark' },
  { key: 'is_active', label: 'Aktif' }
];

export default async function PlansPage() {
  const rows = await adminFetch<Record<string, unknown>[]>('/api/admin/plans/');
  return (
    <PageContainer
      pageTitle='Plans & Pricing'
      pageDescription='Jalankan scripts/seed_pricing.py untuk mengisi paket default'
    >
      <TableShell columns={columns} rows={rows} empty='Belum ada paket. Seed dulu: python -m scripts.seed_pricing' />
    </PageContainer>
  );
}
