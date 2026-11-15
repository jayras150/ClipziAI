import PageContainer from '@/components/layout/page-container';
import { adminFetch } from '@/lib/clipzi';
import WhisperModelManager, {
  type WhisperModelsData
} from '@/features/settings/components/whisper-model-manager';

export const metadata = { title: 'Admin: Whisper Models' };
export const dynamic = 'force-dynamic';

export default async function WhisperModelsPage() {
  let data: WhisperModelsData | null = null;
  let error = '';
  try {
    data = await adminFetch<WhisperModelsData>('/api/admin/whisper-models');
  } catch (exc) {
    error = exc instanceof Error ? exc.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat model.';
  }

  return (
    <PageContainer
      pageTitle='Whisper Models'
      pageDescription='Scan Google Drive, validasi CT2, dan pilih model aktif untuk worker Vast'
    >
      {error || !data ? (
        <p className='text-destructive text-sm'>{error || 'Data model tidak tersedia.'}</p>
      ) : (
        <WhisperModelManager data={data} />
      )}
    </PageContainer>
  );
}
