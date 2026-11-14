import PageContainer from '@/components/layout/page-container';
import { adminFetch } from '@/lib/clipzi';
import VastPanel, {
  type VastConfigData
} from '@/features/settings/components/vast-panel';

export const metadata = { title: 'Admin: Vast.ai' };
export const dynamic = 'force-dynamic';

export default async function VastSettingsPage() {
  let config: VastConfigData | null = null;
  let envItems: Array<Record<string, unknown>> = [];
  let error = '';
  try {
    const [cfg, env] = await Promise.all([
      adminFetch<VastConfigData>('/api/admin/settings/vast'),
      adminFetch<{ items: Array<Record<string, unknown>> }>('/api/admin/settings/vast/env')
    ]);
    config = cfg;
    envItems = env.items || [];
  } catch (exc) {
    error = exc instanceof Error ? exc.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat setelan Vast.';
  }

  return (
    <PageContainer
      pageTitle='Vast.ai'
      pageDescription='Limit storage/GPU/harga, environment worker, billing, dan koneksi Vast'
    >
      {error || !config ? (
        <p className='text-destructive text-sm'>{error || 'Konfigurasi tidak tersedia.'}</p>
      ) : (
        <VastPanel config={config} envItems={envItems} />
      )}
    </PageContainer>
  );
}
