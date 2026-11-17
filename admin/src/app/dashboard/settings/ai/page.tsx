import PageContainer from '@/components/layout/page-container';
import AiProviderPanel from '@/features/settings/components/ai-provider-panel';
import { adminFetch, type AiConfig, type AiProviderMeta } from '@/lib/clipzi';

export const metadata = { title: 'Admin: AI Settings' };
export const dynamic = 'force-dynamic';

export default async function AiSettingsPage() {
  const [config, providers] = await Promise.all([
    adminFetch<AiConfig>('/api/admin/settings/ai'),
    adminFetch<{ items: AiProviderMeta[] }>('/api/admin/settings/ai/providers')
  ]);
  return (
    <PageContainer
      pageTitle='AI Settings'
      pageDescription='Satu provider, satu API key: atur endpoint & model per kemampuan (metadata, rerank, regenerate, transkripsi)'
    >
      <AiProviderPanel config={config} providers={providers.items} />
    </PageContainer>
  );
}
