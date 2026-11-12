import PageContainer from '@/components/layout/page-container';
import TableShell, { formatDate, type Column } from '@/features/admin/table-shell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { adminFetch } from '@/lib/clipzi';
import { adjustCredits, banUser, unbanUser } from './actions';

export const metadata = { title: 'Admin: Users' };

type UserRow = {
  id: string;
  email: string;
  name: string | null;
  provider: string | null;
  is_active: boolean;
  is_banned: boolean;
  created_at: string;
};

function Actions({ row }: { row: Record<string, unknown> }) {
  const uid = String(row.id);
  const banned = Boolean(row.is_banned);
  return (
    <div className='flex items-center gap-1'>
      <form action={banned ? unbanUser : banUser}>
        <input type='hidden' name='uid' value={uid} />
        <Button size='sm' variant={banned ? 'outline' : 'destructive'} type='submit'>
          {banned ? 'Unban' : 'Ban'}
        </Button>
      </form>
      <form action={adjustCredits} className='flex items-center gap-1'>
        <input type='hidden' name='uid' value={uid} />
        <Input name='amount' type='number' defaultValue={0} className='h-8 w-16' />
        <Button size='sm' variant='secondary' type='submit'>
          Kredit
        </Button>
      </form>
    </div>
  );
}

const columns: Column[] = [
  { key: 'id', label: 'ID', render: (row) => String(row.id).slice(0, 8) },
  { key: 'email', label: 'Email' },
  { key: 'name', label: 'Nama' },
  { key: 'provider', label: 'Provider' },
  { key: 'is_banned', label: 'Banned' },
  { key: 'created_at', label: 'Dibuat', render: (row) => formatDate(row.created_at) },
  { key: 'actions', label: 'Aksi', render: (row) => <Actions row={row} /> }
];

export default async function UsersPage() {
  const users = await adminFetch<UserRow[]>('/api/admin/users/');
  return (
    <PageContainer pageTitle='Users' pageDescription={users.length + ' akun terdaftar'}>
      <TableShell columns={columns} rows={users as unknown as Record<string, unknown>[]} />
    </PageContainer>
  );
}
