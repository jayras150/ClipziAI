import PageContainer from '@/components/layout/page-container';
import AiEndpoints from '@/features/settings/components/ai-endpoints';
import AiForm from '@/features/settings/components/ai-form';
import PromptEditor from '@/features/settings/components/prompt-editor';
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
      pageDescription='Provider, daftar model (dengan pencarian), dan batas waktu AI'
    >
      <div className='space-y-4'>
        <AiForm config={config} providers={providers.items} />
        <AiEndpoints
          endpoints={config.endpoints || []}
          active={config.active_endpoints || {}}
          providers={providers.items}
        />
        <PromptEditor />
      </div>
    </PageContainer>
  );
}
