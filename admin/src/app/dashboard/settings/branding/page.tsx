import PageContainer from '@/components/layout/page-container';
import { AdminErrorCard } from '@/components/admin-error-card';
import BrandingForm from '@/features/settings/components/branding-form';
import { adminFetchSafe, type BrandingConfig } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Branding' };

export default async function BrandingPage() {
  const configResult = await adminFetchSafe<BrandingConfig>('/api/admin/settings/branding');
  const config = configResult.data;
  const configError = configResult.error;

  if (!config || configError) {
    return (
      <PageContainer pageTitle='Branding'>
        <AdminErrorCard title='Gagal memuat branding' message={configError ?? 'Data tidak tersedia.'} />
      </PageContainer>
    );
  }
  return (
    <PageContainer pageTitle='Branding' pageDescription='Nama, logo, favicon, warna aksen'>
      <BrandingForm config={config} />
    </PageContainer>
  );
}
