import PageContainer from '@/components/layout/page-container';
import TableShell, { formatDate, type Column } from '@/features/admin/table-shell';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Audit' };

const columns: Column[] = [
  { key: 'created_at', label: 'Waktu', render: (row) => formatDate(row.created_at) },
  { key: 'actor_type', label: 'Aktor' },
  { key: 'actor_email', label: 'Email' },
  { key: 'action', label: 'Aksi' },
  { key: 'resource_type', label: 'Resource' },
  { key: 'resource_id', label: 'ID', render: (row) => String(row.resource_id ?? '').slice(0, 12) },
  { key: 'ip_address', label: 'IP' }
];

export default async function AuditPage() {
  const rows = await adminFetch<Record<string, unknown>[]>('/api/admin/audit/');
  return (
    <PageContainer pageTitle='Audit Log' pageDescription={rows.length + ' entri terakhir'}>
      <TableShell columns={columns} rows={rows} empty='Belum ada aktivitas admin.' />
    </PageContainer>
  );
}
