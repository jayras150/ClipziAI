import PageContainer from '@/components/layout/page-container';
import AiForm from '@/features/settings/components/ai-form';
import { adminFetch, type AiConfig } from '@/lib/clipzi';

export const metadata = { title: 'Admin: AI Settings' };

export default async function AiSettingsPage() {
  const config = await adminFetch<AiConfig>('/api/admin/settings/ai');
  return (
    <PageContainer pageTitle='AI Settings' pageDescription='Provider, model, dan batas waktu AI'>
      <AiForm config={config} />
    </PageContainer>
  );
}
