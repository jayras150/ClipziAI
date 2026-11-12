import PageContainer from '@/components/layout/page-container';
import TableShell, { formatDate, type Column } from '@/features/admin/table-shell';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Transactions' };

const columns: Column[] = [
  { key: 'id', label: 'ID', render: (row) => String(row.id ?? '').slice(0, 8) },
  { key: 'user_id', label: 'User', render: (row) => String(row.user_id ?? '').slice(0, 8) },
  { key: 'amount', label: 'Nominal', render: (row) => 'Rp ' + Number(row.amount ?? 0).toLocaleString('id-ID') },
  { key: 'currency', label: 'Mata uang' },
  { key: 'status', label: 'Status' },
  { key: 'payment_method', label: 'Metode' },
  { key: 'created_at', label: 'Dibuat', render: (row) => formatDate(row.created_at) }
];

export default async function TransactionsPage() {
  const rows = await adminFetch<Record<string, unknown>[]>('/api/admin/transactions/');
  return (
    <PageContainer pageTitle='Transactions' pageDescription={rows.length + ' transaksi terakhir'}>
      <TableShell columns={columns} rows={rows} empty='Belum ada transaksi.' />
    </PageContainer>
  );
}
