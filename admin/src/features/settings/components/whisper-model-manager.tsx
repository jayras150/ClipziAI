'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import {
  activateWhisperModel,
  deleteWhisperModel,
  downloadWhisperColabNotebook,
  saveWhisperColabNotebook,
  scanWhisperModels
} from '@/app/dashboard/settings/models/actions';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';


export type WhisperModelItem = {
  id: string;
  slug: string;
  label: string;
  drive_folder_id: string;
  drive_path: string;
  model_type: string;
  status: string;
  validation_error: string | null;
  size_bytes: number;
  file_count: number;
  files: string[];
  is_active: boolean;
  last_scanned_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type WhisperModelsData = {
  configured: boolean;
  enabled: boolean;
  folder_id: string;
  root_path: string;
  service_account_email: string;
  error: string;
  active_model_id: string | null;
  active_model: WhisperModelItem | null;
  items: WhisperModelItem[];
  notebook_file_id: string;
  notebook_url: string;
  folder_url: string;
};

function formatBytes(value: number): string {
  if (!value) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const amount = value / 1024 ** index;
  return `${amount.toFixed(index >= 3 ? 2 : 1)} ${units[index]}`;
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return value;
  }
}

function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'available') return 'secondary';
  if (status === 'missing' || status === 'error' || status === 'invalid') return 'destructive';
  return 'outline';
}

export default function WhisperModelManager({ data }: { data: WhisperModelsData }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [notebookId, setNotebookId] = useState(data.notebook_file_id || '');
  const [colabUrl, setColabUrl] = useState(data.notebook_url || '');

  const runScan = () => {
    setError('');
    setMessage('');
    startTransition(async () => {
      const response = await scanWhisperModels();
      if ('error' in response) {
        setError(String(response.error));
        return;
      }
      const result = response.data as Record<string, unknown> | undefined;
      setMessage(
        `Scan selesai: ${result?.created ?? 0} baru, ${result?.updated ?? 0} diperbarui, ${
          result?.missing ?? 0
        } hilang, total ${result?.total ?? 0}.`
      );
      router.refresh();
    });
  };

  const runDownloadNotebook = () => {
    setError('');
    setMessage('');
    startTransition(async () => {
      const response = await downloadWhisperColabNotebook();
      if ('error' in response || !response.data) {
        setError(String(('error' in response && response.error) || 'Gagal mengunduh notebook.'));
        return;
      }
      const data = response.data;
      const blob = new Blob([data.content], { type: 'application/x-ipynb+json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = data.filename || 'clipzi-whisper-colab.ipynb';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage('Notebook diunduh. Upload file .ipynb itu ke Google Drive sekali, lalu tempel file ID-nya di bawah.');
    });
  };

  const runSaveNotebook = () => {
    setError('');
    setMessage('');
    startTransition(async () => {
      const response = await saveWhisperColabNotebook(notebookId);
      if ('error' in response || !response.data) {
        setError(String(('error' in response && response.error) || 'Gagal menyimpan file ID.'));
        return;
      }
      const result = response.data as Record<string, unknown>;
      setNotebookId(String(result.notebook_file_id || ''));
      setColabUrl(String(result.notebook_url || ''));
      setMessage(
        result.notebook_url
          ? 'File ID notebook tersimpan. Tombol Buka Colab sudah aktif.'
          : 'File ID dikosongkan.'
      );
      router.refresh();
    });
  };

  const openColab = () => {
    if (!colabUrl) {
      setError('Simpan file ID notebook Google Drive terlebih dahulu.');
      return;
    }
    window.open(colabUrl, '_blank', 'noopener,noreferrer');
  };

  const runActivate = (item: WhisperModelItem) => {
    if (!window.confirm(`Aktifkan model "${item.label}" untuk semua worker berikutnya?`)) {
      return;
    }
    setError('');
    setMessage('');
    startTransition(async () => {
      const response = await activateWhisperModel(item.id);
      if ('error' in response) {
        setError(String(response.error));
        return;
      }
      setMessage(`Model "${item.label}" aktif. Restore Vast diarahkan ke ${item.drive_path}.`);
      router.refresh();
    });
  };

  const runDelete = (item: WhisperModelItem, deleteDrive: boolean) => {
    const suffix = deleteDrive
      ? ' Folder dan semua file di Google Drive juga akan DIHAPUS permanen.'
      : ' Model hanya dihapus dari daftar admin; folder Drive tetap ada.';
    if (!window.confirm(`Hapus "${item.label}"?${suffix}`)) return;
    setError('');
    setMessage('');
    startTransition(async () => {
      const response = await deleteWhisperModel(item.id, deleteDrive);
      if ('error' in response) {
        setError(String(response.error));
        return;
      }
      setMessage(
        deleteDrive
          ? `Model dan folder Drive dihapus (${String(
              (response.data as Record<string, unknown> | undefined)?.drive_objects_removed ?? 0
            )} objek).`
          : 'Model dihapus dari daftar admin.'
      );
      router.refresh();
    });
  };

  const active = data.active_model || data.items.find((item) => item.is_active) || null;

  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle>Google Drive model registry</CardTitle>
          <CardDescription>
            Folder root: <code>{data.root_path}</code>. Upload model CT2 lewat Colab ke folder
            ini, lalu tekan Scan Drive. Model yang valid bisa diaktifkan tanpa deploy ulang.
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='grid gap-2 text-sm md:grid-cols-2'>
            <div>
              <span className='text-muted-foreground'>Folder ID: </span>
              <code className='break-all'>{data.folder_id || '—'}</code>
            </div>
            <div>
              <span className='text-muted-foreground'>Service account: </span>
              <code className='break-all'>{data.service_account_email || '—'}</code>
            </div>
            <div>
              <span className='text-muted-foreground'>Status Drive: </span>
              <Badge variant={data.configured ? 'secondary' : 'destructive'}>
                {data.configured ? 'configured' : 'belum siap'}
              </Badge>
            </div>
            <div>
              <span className='text-muted-foreground'>Model aktif: </span>
              {active ? <Badge>{active.label}</Badge> : <span>belum ada</span>}
            </div>
          </div>

          {data.error ? <p className='text-destructive text-sm'>{data.error}</p> : null}
          {!data.configured ? (
            <p className='text-destructive text-sm'>
              Isi <code>GDRIVE_SERVICE_ACCOUNT_B64</code>, <code>GDRIVE_FOLDER_ID</code>, dan{' '}
              <code>GDRIVE_ENABLED=true</code> di backend/.env lalu recreate container.
            </p>
          ) : null}

          <div className='flex flex-wrap items-center gap-2'>
            <Button type='button' disabled={pending || !data.configured} onClick={runScan}>
              {pending ? 'Memproses…' : 'Scan Drive'}
            </Button>
            {message ? <p className='text-muted-foreground text-sm'>{message}</p> : null}
            {error ? <p className='text-destructive text-sm'>{error}</p> : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Upload model lewat Colab</CardTitle>
          <CardDescription>
            Notebook berisi kode lengkap untuk connect ke Drive, mengunduh model, konversi CT2,
            dan menyimpan ke folder ID di atas. Upload notebook ke Drive sekali, lalu buka lewat
            tombol Colab.
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='flex flex-wrap items-center gap-2'>
            <Button type='button' disabled={pending} onClick={runDownloadNotebook}>
              Unduh notebook
            </Button>
            <Button
              type='button'
              variant='outline'
              disabled={pending || !colabUrl}
              onClick={openColab}
            >
              Buka Colab
            </Button>
            {data.folder_url ? (
              <a
                href={data.folder_url}
                target='_blank'
                rel='noreferrer'
                className='text-primary text-sm underline'
              >
                Buka folder Drive
              </a>
            ) : null}
          </div>

          <div className='grid gap-2 md:grid-cols-[1fr_auto]'>
            <div className='space-y-1'>
              <label className='text-muted-foreground text-xs'>Notebook Drive File ID</label>
              <Input
                value={notebookId}
                onChange={(event) => setNotebookId(event.target.value)}
                placeholder='Contoh: 1AbCdEfGhIjKlMnOpQrStUvWxYz'
              />
            </div>
            <div className='flex items-end'>
              <Button type='button' disabled={pending} onClick={runSaveNotebook}>
                Simpan ID
              </Button>
            </div>
          </div>

          <ol className='text-muted-foreground list-decimal space-y-1 pl-5 text-sm'>
            <li>Klik <strong>Unduh notebook</strong>.</li>
            <li>Upload file <code>.ipynb</code> ke Google Drive (sekali saja).</li>
            <li>Copy file ID dari URL Drive, tempel di kolom di atas, lalu simpan.</li>
            <li>Klik <strong>Buka Colab</strong> → pilih model → <strong>Run all</strong>.</li>
            <li>Setelah selesai, kembali ke sini → <strong>Scan Drive</strong> → <strong>Aktifkan</strong>.</li>
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Daftar model</CardTitle>
          <CardDescription>
            Hanya folder dengan <code>model.bin</code>, <code>config.json</code>,{' '}
            <code>tokenizer.json</code>, <code>preprocessor_config.json</code>, dan vocabulary
            yang bisa diaktifkan.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {data.items.length === 0 ? (
            <div className='text-muted-foreground space-y-2 text-sm'>
              <p>Belum ada model di registry.</p>
              <p>
                Buat folder model di Drive (contoh <code>large-v3</code>), upload hasil konversi
                CT2, lalu tekan <strong>Scan Drive</strong>.
              </p>
            </div>
          ) : (
            <div className='overflow-x-auto'>
              <table className='w-full min-w-[760px] text-left text-sm'>
                <thead className='text-muted-foreground border-b text-xs uppercase'>
                  <tr>
                    <th className='py-2 pr-3'>Model</th>
                    <th className='py-2 pr-3'>Ukuran</th>
                    <th className='py-2 pr-3'>File</th>
                    <th className='py-2 pr-3'>Status</th>
                    <th className='py-2 pr-3'>Scan terakhir</th>
                    <th className='py-2'>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={item.id} className='border-b align-top last:border-0'>
                      <td className='py-3 pr-3'>
                        <div className='font-medium'>{item.label}</div>
                        <div className='text-muted-foreground break-all text-xs'>
                          {item.drive_path}
                        </div>
                      </td>
                      <td className='py-3 pr-3 whitespace-nowrap'>
                        {formatBytes(item.size_bytes)}
                      </td>
                      <td className='py-3 pr-3'>{item.file_count}</td>
                      <td className='py-3 pr-3'>
                        <div className='flex flex-wrap gap-1'>
                          <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                          {item.is_active ? <Badge>aktif</Badge> : null}
                        </div>
                        {item.validation_error ? (
                          <p className='text-destructive mt-1 max-w-xs text-xs'>
                            {item.validation_error}
                          </p>
                        ) : null}
                      </td>
                      <td className='text-muted-foreground py-3 pr-3 whitespace-nowrap text-xs'>
                        {formatDate(item.last_scanned_at)}
                      </td>
                      <td className='py-3'>
                        <div className='flex flex-wrap gap-2'>
                          <Button
                            type='button'
                            size='sm'
                            variant='outline'
                            disabled={pending || item.is_active || item.status !== 'available'}
                            onClick={() => runActivate(item)}
                          >
                            {item.is_active ? 'Aktif' : 'Aktifkan'}
                          </Button>
                          <Button
                            type='button'
                            size='sm'
                            variant='ghost'
                            disabled={pending || item.is_active}
                            onClick={() => runDelete(item, false)}
                          >
                            Hapus daftar
                          </Button>
                          <Button
                            type='button'
                            size='sm'
                            variant='destructive'
                            disabled={pending || item.is_active || item.status === 'missing'}
                            onClick={() => runDelete(item, true)}
                          >
                            Hapus + Drive
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


