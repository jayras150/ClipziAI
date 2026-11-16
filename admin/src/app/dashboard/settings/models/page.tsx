import PageContainer from '@/components/layout/page-container';
import { adminFetch } from '@/lib/clipzi';
import WhisperModelManager, {
  type WhisperModelsData
} from '@/features/settings/components/whisper-model-manager';
import WhisperSourcePanel, {
  type WhisperSourceData
} from '@/features/settings/components/whisper-source-panel';

export const metadata = { title: 'Admin: Whisper Models' };
export const dynamic = 'force-dynamic';

export default async function WhisperModelsPage() {
  let data: WhisperModelsData | null = null;
  let source: WhisperSourceData | null = null;
  let error = '';
  try {
    data = await adminFetch<WhisperModelsData>('/api/admin/whisper-models');
  } catch (exc) {
    error = exc instanceof Error ? exc.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat model.';
  }
  try {
    source = await adminFetch<WhisperSourceData>('/api/admin/whisper-models/source');
  } catch {
    source = null;
  }

  return (
    <PageContainer
      pageTitle='Whisper Models'
      pageDescription='Pilih provider model (Google Drive, Dropbox, Backblaze, Hugging Face, S3), scan CT2, dan aktifkan untuk worker Vast'
    >
      <div className='space-y-4'>
        {source ? <WhisperSourcePanel data={source} /> : null}
        {error || !data ? (
          <p className='text-destructive text-sm'>{error || 'Data model tidak tersedia.'}</p>
        ) : (
          <WhisperModelManager data={data} />
        )}
      </div>
    </PageContainer>
  );
}
