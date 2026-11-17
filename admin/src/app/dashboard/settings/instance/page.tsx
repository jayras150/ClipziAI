import PageContainer from '@/components/layout/page-container';
import InstancePanel from '@/features/settings/components/instance-panel';
import type { VastConfigData } from '@/features/settings/components/vast-panel';
import type { VastTemplateStatus } from '@/app/dashboard/settings/vast/actions';
import type { WhisperModelsData } from '@/features/settings/components/whisper-model-manager';
import type { WhisperSourceData } from '@/features/settings/components/whisper-source-panel';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Instance & Worker' };
export const dynamic = 'force-dynamic';

export default async function InstanceSettingsPage({
  searchParams
}: {
  searchParams?: { tab?: string };
}) {
  let config: VastConfigData | null = null;
  let envItems: Array<Record<string, unknown>> = [];
  let template: VastTemplateStatus | null = null;
  let whisper: WhisperModelsData | null = null;
  let source: WhisperSourceData | null = null;
  let error = '';

  try {
    const [cfg, env, tpl] = await Promise.all([
      adminFetch<VastConfigData>('/api/admin/settings/vast'),
      adminFetch<{ items: Array<Record<string, unknown>> }>('/api/admin/settings/vast/env'),
      adminFetch<VastTemplateStatus>('/api/admin/settings/vast/template')
    ]);
    config = cfg;
    envItems = env.items || [];
    template = tpl;
  } catch (exc) {
    error = exc instanceof Error ? exc.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat setelan instance.';
  }

  try {
    whisper = await adminFetch<WhisperModelsData>('/api/admin/whisper-models');
  } catch {
    whisper = null;
  }
  try {
    source = await adminFetch<WhisperSourceData>('/api/admin/whisper-models/source');
  } catch {
    source = null;
  }

  return (
    <PageContainer
      pageTitle='Instance & Worker'
      pageDescription='Vast.ai, satu worker template (auto memuat model aktif), model Whisper, dan sumber model — semua di satu tempat'
    >
      {error || !config || !template ? (
        <p className='text-destructive text-sm'>{error || 'Konfigurasi instance tidak tersedia.'}</p>
      ) : (
        <InstancePanel
          config={config}
          envItems={envItems}
          template={template}
          whisper={whisper}
          source={source}
          initialTab={searchParams?.tab}
        />
      )}
    </PageContainer>
  );
}
