import PageContainer from '@/components/layout/page-container';
import BrandingForm from '@/features/settings/components/branding-form';
import { adminFetch, type BrandingConfig } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Branding' };

export default async function BrandingPage() {
  const config = await adminFetch<BrandingConfig>('/api/admin/settings/branding');
  return (
    <PageContainer pageTitle='Branding' pageDescription='Nama, logo, favicon, warna aksen'>
      <BrandingForm config={config} />
    </PageContainer>
  );
}
