'use client';

import { useRef, useState, useTransition } from 'react';

import {
  saveBranding,
  uploadBrandingAsset,
  type UploadedAsset
} from '@/app/dashboard/settings/actions';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ClipzySpinner } from '@/components/ui/clipzy-spinner';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { BrandingConfig } from '@/lib/clipzi';

type AssetKind = 'logo' | 'favicon' | 'og';

const KIND_LABEL: Record<AssetKind, string> = {
  logo: 'Logo',
  favicon: 'Favicon',
  og: 'OG Image'
};

const KIND_HINT: Record<AssetKind, string> = {
  logo: 'PNG/SVG transparan, tinggi ideal 64–256 px. Muncul di navbar, header, dan footer.',
  favicon: 'PNG/ICO 32–512 px. Muncul di tab browser dan bookmark.',
  og: 'PNG/JPG 1200×630 px. Muncul saat link dibagikan di sosial media.'
};

function humanSize(bytes?: number): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Kartu pratinjau aset branding.
 *
 * Sebelumnya upload hanya menampilkan pesan teks, sehingga admin tidak tahu
 * apakah logo benar, ukurannya pas, atau favicon muncul di tab. Sekarang setiap
 * aset punya kartu dengan pratinjau nyata + info dimensi/ukuran.
 */
function AssetCard({
  kind,
  url,
  asset,
  uploading,
  onFile,
  onRemove
}: {
  kind: AssetKind;
  url: string;
  asset?: UploadedAsset;
  uploading: boolean;
  onFile: (file: File | null) => void;
  onRemove: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localPreview, setLocalPreview] = useState('');

  const preview = localPreview || url;

  const pick = (file: File | null) => {
    if (!file) return;
    setLocalPreview(URL.createObjectURL(file));
    onFile(file);
  };

  return (
    <Card className='overflow-hidden'>
      <CardHeader className='pb-3'>
        <div className='flex items-center justify-between'>
          <CardTitle className='text-base'>{KIND_LABEL[kind]}</CardTitle>
          {uploading ? (
            <Badge variant='secondary' className='gap-1'>
              <ClipzySpinner size='xs' variant='ring' /> mengunggah
            </Badge>
          ) : url ? (
            <Badge variant='outline'>aktif</Badge>
          ) : (
            <Badge variant='outline'>default</Badge>
          )}
        </div>
        <CardDescription className='text-xs'>{KIND_HINT[kind]}</CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        {kind === 'favicon' ? (
          <div className='bg-muted/40 flex items-center gap-2 rounded-lg border p-2'>
            <div className='bg-background flex items-center gap-2 rounded-t-md border-b px-3 py-1.5'>
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt='favicon' className='size-4 rounded-sm object-contain' />
              ) : (
                <span className='text-xs'>▶</span>
              )}
              <span className='text-muted-foreground max-w-[120px] truncate text-[11px]'>
                Clipzy AI
              </span>
              <span className='text-muted-foreground/60 text-[11px]'>×</span>
            </div>
            <span className='text-muted-foreground text-xs'>pratinjau tab browser</span>
          </div>
        ) : (
          <div
            className={
              kind === 'logo'
                ? 'grid grid-cols-2 gap-2'
                : 'flex items-center justify-center rounded-lg border p-2'
            }
          >
            <div className='bg-[#0b0d12] flex h-20 items-center justify-center rounded-lg border'>
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt='logo gelap' className='max-h-12 max-w-[80%] object-contain' />
              ) : (
                <span className='text-muted-foreground text-xs'>
                  {kind === 'logo' ? 'logo' : 'OG image'}
                </span>
              )}
            </div>
            {kind === 'logo' ? (
              <div className='flex h-20 items-center justify-center rounded-lg border bg-white'>
                {preview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={preview} alt='logo terang' className='max-h-12 max-w-[80%] object-contain' />
                ) : (
                  <span className='text-muted-foreground text-xs'>logo</span>
                )}
              </div>
            ) : null}
          </div>
        )}

        <div className='text-muted-foreground grid grid-cols-2 gap-1 text-[11px]'>
          <span>
            Dimensi: {asset?.width && asset?.height ? `${asset.width}×${asset.height}` : '-'}
          </span>
          <span>Ukuran: {humanSize(asset?.size_bytes)}</span>
          <span className='col-span-2 truncate'>{url || 'belum ada (memakai default)'}</span>
        </div>

        <div
          className={`rounded-lg border border-dashed p-2 text-center text-xs transition ${
            dragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/30'
          }`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            pick(event.dataTransfer.files?.[0] || null);
          }}
        >
          Tarik file ke sini, atau
          <button
            type='button'
            className='text-primary ml-1 underline'
            onClick={() => inputRef.current?.click()}
          >
            pilih file
          </button>
          <input
            ref={inputRef}
            type='file'
            accept='image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon,image/vnd.microsoft.icon'
            className='hidden'
            onChange={(event) => pick(event.target.files?.[0] || null)}
          />
        </div>

        <div className='flex gap-2'>
          <Button
            size='sm'
            variant='outline'
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
          >
            {url ? 'Ganti' : 'Unggah'}
          </Button>
          <Button size='sm' variant='ghost' onClick={onRemove} disabled={!url || uploading}>
            Hapus
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function BrandingForm({ config }: { config: BrandingConfig }) {
  const [form, setForm] = useState({
    app_name: config.app_name,
    tagline: config.tagline || '',
    accent_color: config.accent_color,
    support_email: config.support_email || '',
    footer_note: config.footer_note || '',
    logo_url: config.logo_url || '',
    favicon_url: config.favicon_url || '',
    og_image_url: config.og_image_url || ''
  });
  const [assets, setAssets] = useState<Partial<Record<AssetKind, UploadedAsset>>>({});
  const [uploading, setUploading] = useState<AssetKind | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [pending, startTransition] = useTransition();

  const set = (key: keyof typeof form, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const urlKey: Record<AssetKind, 'logo_url' | 'favicon_url' | 'og_image_url'> = {
    logo: 'logo_url',
    favicon: 'favicon_url',
    og: 'og_image_url'
  };

  const onSave = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await saveBranding(form);
      if (result.ok) setMessage('Branding tersimpan dan langsung dipakai semua halaman.');
      else setError(result.error || 'Gagal menyimpan.');
    });
  };

  const onUpload = (kind: AssetKind, file: File | null) => {
    if (!file) return;
    setMessage('');
    setError('');
    setUploading(kind);
    startTransition(async () => {
      const data = new FormData();
      data.set('kind', kind);
      data.set('file', file);
      const result = await uploadBrandingAsset(data);
      setUploading(null);
      if (result.ok && result.asset) {
        // Form langsung memakai URL baru: tidak perlu reload halaman lagi.
        set(urlKey[kind], result.asset.url);
        setAssets((prev) => ({ ...prev, [kind]: result.asset as UploadedAsset }));
        setMessage(`${KIND_LABEL[kind]} terunggah (${humanSize(result.asset.size_bytes)}).`);
      } else {
        setError(result.error || 'Gagal mengunggah.');
      }
    });
  };

  const onRemove = (kind: AssetKind) => {
    set(urlKey[kind], '');
    setAssets((prev) => ({ ...prev, [kind]: undefined }));
    setMessage(`${KIND_LABEL[kind]} akan dihapus setelah klik Simpan.`);
  };

  return (
    <div className='space-y-4'>
      <div className='grid gap-4 md:grid-cols-3'>
        <AssetCard
          kind='logo'
          url={form.logo_url}
          asset={assets.logo}
          uploading={uploading === 'logo'}
          onFile={(file) => onUpload('logo', file)}
          onRemove={() => onRemove('logo')}
        />
        <AssetCard
          kind='favicon'
          url={form.favicon_url}
          asset={assets.favicon}
          uploading={uploading === 'favicon'}
          onFile={(file) => onUpload('favicon', file)}
          onRemove={() => onRemove('favicon')}
        />
        <AssetCard
          kind='og'
          url={form.og_image_url}
          asset={assets.og}
          uploading={uploading === 'og'}
          onFile={(file) => onUpload('og', file)}
          onRemove={() => onRemove('og')}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Identitas</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-4 md:grid-cols-2'>
          <div className='space-y-2'>
            <Label htmlFor='app_name'>Nama aplikasi</Label>
            <Input id='app_name' value={form.app_name} onChange={(e) => set('app_name', e.target.value)} />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='accent_color'>Warna aksen</Label>
            <div className='flex gap-2'>
              <Input
                id='accent_color'
                value={form.accent_color}
                onChange={(e) => set('accent_color', e.target.value)}
              />
              <span
                className='size-9 shrink-0 rounded-md border'
                style={{ background: form.accent_color }}
                aria-label='pratinjau warna aksen'
              />
            </div>
          </div>
          <div className='space-y-2 md:col-span-2'>
            <Label htmlFor='tagline'>Tagline</Label>
            <Input id='tagline' value={form.tagline} onChange={(e) => set('tagline', e.target.value)} />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='support_email'>Email dukungan</Label>
            <Input
              id='support_email'
              value={form.support_email}
              onChange={(e) => set('support_email', e.target.value)}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='footer_note'>Catatan footer</Label>
            <Input
              id='footer_note'
              value={form.footer_note}
              onChange={(e) => set('footer_note', e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {message ? <Badge variant='secondary'>{message}</Badge> : null}
      {error ? <p className='text-destructive text-sm'>{error}</p> : null}

      <Button onClick={onSave} disabled={pending || uploading !== null} className='gap-2'>
        {pending ? <ClipzySpinner size='xs' variant='ring' /> : null}
        {pending ? 'Menyimpan…' : 'Simpan branding'}
      </Button>
    </div>
  );
}

