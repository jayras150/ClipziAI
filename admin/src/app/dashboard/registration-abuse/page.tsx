import PageContainer from '@/components/layout/page-container';
import { adminFetch } from '@/lib/clipzi';
import RegistrationAbusePanel, {
  type RegistrationAbuseData
} from '@/features/registration-abuse/components/registration-abuse-panel';

export const metadata = { title: 'Admin: Registration Abuse' };
export const dynamic = 'force-dynamic';

export default async function RegistrationAbusePage() {
  let data: RegistrationAbuseData | null = null;
  let error = '';
  try {
    data = await adminFetch<RegistrationAbuseData>(
      '/api/admin/registration-abuse?page=1&page_size=50'
    );
  } catch (exc) {
    error = exc instanceof Error ? exc.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat device.';
  }

  return (
    <PageContainer
      pageTitle='Registration Abuse'
      pageDescription='Deteksi perangkat, akun terkait, dan klaim kredit Free yang berulang'
    >
      {error || !data ? (
        <p className='text-destructive text-sm'>{error || 'Data tidak tersedia.'}</p>
      ) : (
        <RegistrationAbusePanel data={data} />
      )}
    </PageContainer>
  );
}
