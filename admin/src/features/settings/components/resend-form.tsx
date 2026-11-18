'use client';

import { useState, useTransition } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { saveSmtp, testSmtp } from '@/app/dashboard/settings/smtp/actions';

type Config = {
  provider?: string;
  resend_key_set?: boolean;
  resend_key_preview?: string;
  from_email?: string;
  from_name?: string;
  enabled?: boolean;
};

/** Kirim email via Resend.com API (alternatif SMTP). */
export default function ResendForm({ config }: { config: Config }) {
  const [provider, setProvider] = useState(config.provider || 'smtp');
  const [apiKey, setApiKey] = useState('');
  const [fromEmail, setFromEmail] = useState(config.from_email || '');
  const [fromName, setFromName] = useState(config.from_name || 'Clipzy AI');
  const [to, setTo] = useState('');
  const [message, setMessage] = useState('');
  const [pending, startTransition] = useTransition();

  const save = () => {
    startTransition(async () => {
      const result = await saveSmtp({
        provider,
        resend_api_key: apiKey || undefined,
        from_email: fromEmail,
        from_name: fromName,
        enabled: true
      });
      setMessage(result.ok ? 'Tersimpan. Provider email: ' + provider : result.error || 'Gagal menyimpan.');
      if (result.ok) setApiKey('');
    });
  };

  const sendTest = () => {
    if (!to.trim()) {
      setMessage('Isi email tujuan dulu.');
      return;
    }
    startTransition(async () => {
      const result = await testSmtp(to.trim());
      setMessage(result.ok ? 'Email uji terkirim lewat ' + provider + '.' : result.error || 'Gagal kirim.');
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Provider Email (Resend API)</CardTitle>
        <CardDescription>
          Selain SMTP, email bisa dikirim lewat Resend.com API. Domain pengirim harus sudah diverifikasi di Resend.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='grid gap-3 md:grid-cols-2'>
          <div className='space-y-1'>
            <Label>Provider</Label>
            <select
              className='border-input bg-background h-9 w-full rounded-md border px-3 text-sm'
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
            >
              <option value='smtp'>SMTP (host/port di atas)</option>
              <option value='resend'>Resend.com API</option>
            </select>
          </div>
          <div className='space-y-1'>
            <Label>
              Resend API key {config.resend_key_set ? `(tersimpan ${config.resend_key_preview || ''})` : ''}
            </Label>
            <Input
              type='password'
              value={apiKey}
              placeholder={config.resend_key_set ? 'kosong = tidak diubah' : 're_...'}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </div>
          <div className='space-y-1'>
            <Label>From email (domain terverifikasi)</Label>
            <Input value={fromEmail} onChange={(event) => setFromEmail(event.target.value)} />
          </div>
          <div className='space-y-1'>
            <Label>From name</Label>
            <Input value={fromName} onChange={(event) => setFromName(event.target.value)} />
          </div>
          <div className='space-y-1'>
            <Label>Email tujuan (test)</Label>
            <Input value={to} onChange={(event) => setTo(event.target.value)} placeholder='admin@domain.com' />
          </div>
        </div>
        <div className='flex flex-wrap gap-2'>
          <Button onClick={save} disabled={pending}>
            Simpan provider
          </Button>
          <Button variant='outline' onClick={sendTest} disabled={pending}>
            Kirim test
          </Button>
        </div>
        {message ? <p className='text-xs text-emerald-600'>{message}</p> : null}
      </CardContent>
    </Card>
  );
}
