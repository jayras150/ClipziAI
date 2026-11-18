import PageContainer from '@/components/layout/page-container';
import WorkersTable from '@/features/settings/components/workers-table';

export const metadata = { title: 'Admin: Worker Logs' };
export const dynamic = 'force-dynamic';

export default function WorkersPage() {
  return (
    <PageContainer
      pageTitle='Worker Logs'
      pageDescription='Klik salah satu task untuk melihat status + log realtime dari dalam instance worker.'
    >
      <WorkersTable />
    </PageContainer>
  );
}
