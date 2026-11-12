"use client";

import { useState, useTransition } from 'react';

import { saveBranding, uploadBrandingAsset } from '@/app/dashboard/settings/actions';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { BrandingConfig } from '@/lib/clipzi';

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
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [pending, startTransition] = useTransition();

  const set = (key: keyof typeof form, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const onSave = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await saveBranding(form);
      if (result.ok) setMessage('Branding tersimpan. Frontend memakai nilai ini pada request berikutnya.');
      else setError(result.error || 'Gagal menyimpan.');
    });
  };

  const onUpload = (kind: 'logo' | 'favicon', file: File | null) => {
    if (!file) return;
    setMessage('');
    setError('');
    startTransition(async () => {
      const data = new FormData();
      data.set('kind', kind);
      data.set('file', file);
      const result = await uploadBrandingAsset(data);
      if (result.ok) setMessage('Aset ' + kind + ' terunggah. Muat ulang halaman untuk melihat URL baru.');
      else setError(result.error || 'Gagal mengunggah.');
    });
  };

  return (
    <div className='space-y-4'>
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
            <Label htmlFor='accent_color'>Warna aksen (#rrggbb)</Label>
            <Input id='accent_color' value={form.accent_color} onChange={(e) => set('accent_color', e.target.value)} />
          </div>
          <div className='space-y-2 md:col-span-2'>
            <Label htmlFor='tagline'>Tagline</Label>
            <Input id='tagline' value={form.tagline} onChange={(e) => set('tagline', e.target.value)} />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='support_email'>Email support</Label>
            <Input id='support_email' value={form.support_email} onChange={(e) => set('support_email', e.target.value)} />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='footer_note'>Catatan footer</Label>
            <Input id='footer_note' value={form.footer_note} onChange={(e) => set('footer_note', e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Logo & favicon</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-4 md:grid-cols-2'>
          <div className='space-y-2'>
            <Label>Logo (PNG/JPEG/WEBP/SVG, maks 2 MB)</Label>
            <input
              type='file'
              accept='image/png,image/jpeg,image/webp,image/svg+xml'
              className='text-sm'
              onChange={(event) => onUpload('logo', event.target.files?.[0] ?? null)}
            />
            {form.logo_url ? <p className='text-muted-foreground text-xs break-all'>{form.logo_url}</p> : null}
          </div>
          <div className='space-y-2'>
            <Label>Favicon (PNG/ICO/SVG, maks 2 MB)</Label>
            <input
              type='file'
              accept='image/png,image/x-icon,image/vnd.microsoft.icon,image/svg+xml'
              className='text-sm'
              onChange={(event) => onUpload('favicon', event.target.files?.[0] ?? null)}
            />
            {form.favicon_url ? <p className='text-muted-foreground text-xs break-all'>{form.favicon_url}</p> : null}
          </div>
        </CardContent>
      </Card>

      {message ? <Badge variant='secondary'>{message}</Badge> : null}
      {error ? <p className='text-destructive text-sm'>{error}</p> : null}

      <Button onClick={onSave} disabled={pending}>
        {pending ? 'Menyimpan...' : 'Simpan branding'}
      </Button>
    </div>
  );
}
