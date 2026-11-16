'use client';

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

import { saveSmtp, sendNotify, sendReport, testSmtp } from '@/app/dashboard/settings/smtp/actions';

export type SmtpConfig = {
  enabled: boolean;
  host: string;
  port: number;
  username: string;
  from_email: string;
  from_name: string;
  use_tls: boolean;
  use_ssl: boolean;
  reply_to: string;
  password_set: boolean;
  password_preview: string;
  types: Record<string, boolean>;
};

export type SmtpData = { config: SmtpConfig; kinds: string[] };

const KIND_LABELS: Record<string, string> = {
  welcome: 'Welcome email on signup',
  verify: 'Account verification email',
  otp: 'OTP codes',
  reset: 'Password reset link',
  notify: 'User notifications',
  report: 'Automatic reports'
};

export default function SmtpForm({ data }: { data: SmtpData }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [config, setConfig] = useState<SmtpConfig>(data.config);
  const [password, setPassword] = useState('');
  const [testTo, setTestTo] = useState('');
  const [subject, setSubject] = useState('Clipzy AI update');
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const set = <K extends keyof SmtpConfig>(key: K, value: SmtpConfig[K]) =>
    setConfig((prev) => ({ ...prev, [key]: value }));

  const run = (fn: () => Promise<{ ok: boolean; error?: string }>, success: string) => {
    setNotice('');
    setError('');
    startTransition(async () => {
      const result = await fn();
      if (!result.ok) {
        setError(result.error || 'Request failed.');
        return;
      }
      setNotice(success);
      router.refresh();
    });
  };

  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle>SMTP server</CardTitle>
          <CardDescription>Used for verification, OTP, password reset, notifications and reports.</CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='flex items-center gap-3'>
            <Switch checked={config.enabled} onCheckedChange={(value) => set('enabled', value)} />
            <Label>Enable email sending</Label>
          </div>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='space-y-1'>
              <Label htmlFor='smtp-host'>Host</Label>
              <Input id='smtp-host' value={config.host} onChange={(e) => set('host', e.target.value)} placeholder='smtp.gmail.com' />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='smtp-port'>Port</Label>
              <Input id='smtp-port' type='number' value={config.port} onChange={(e) => set('port', Number(e.target.value) || 587)} />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='smtp-user'>Username</Label>
              <Input id='smtp-user' value={config.username} onChange={(e) => set('username', e.target.value)} placeholder='noreply@domain.com' />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='smtp-pass'>Password</Label>
              <Input id='smtp-pass' type='password' value={password} onChange={(e) => setPassword(e.target.value)} placeholder={config.password_set ? 'Saved - leave blank to keep' : 'SMTP password'} />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='smtp-from'>From email</Label>
              <Input id='smtp-from' value={config.from_email} onChange={(e) => set('from_email', e.target.value)} />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='smtp-name'>From name</Label>
              <Input id='smtp-name' value={config.from_name} onChange={(e) => set('from_name', e.target.value)} />
            </div>
          </div>
          <div className='flex flex-wrap gap-4'>
            <label className='flex items-center gap-2 text-sm'>
              <Switch checked={config.use_tls} onCheckedChange={(value) => set('use_tls', value)} /> STARTTLS
            </label>
            <label className='flex items-center gap-2 text-sm'>
              <Switch checked={config.use_ssl} onCheckedChange={(value) => set('use_ssl', value)} /> SSL (465)
            </label>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Email types</CardTitle>
          <CardDescription>Turn each automated email on or off.</CardDescription>
        </CardHeader>
        <CardContent className='grid gap-2 sm:grid-cols-2'>
          {data.kinds.map((kind) => (
            <label key={kind} className='flex items-center gap-2 text-sm'>
              <Switch
                checked={Boolean(config.types?.[kind])}
                onCheckedChange={(value) => set('types', { ...config.types, [kind]: value })}
              />
              {KIND_LABELS[kind] || kind}
            </label>
          ))}
        </CardContent>
      </Card>

      <div className='flex flex-wrap gap-2'>
        <Button
          disabled={pending}
          onClick={() =>
            run(
              () => saveSmtp({ ...config, password }),
              'SMTP settings saved.'
            )
          }
        >
          Save settings
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Send test email</CardTitle>
        </CardHeader>
        <CardContent className='flex flex-wrap items-end gap-2'>
          <div className='min-w-[240px] flex-1 space-y-1'>
            <Label htmlFor='smtp-test'>Recipient</Label>
            <Input id='smtp-test' value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder='you@domain.com' />
          </div>
          <Button variant='secondary' disabled={pending || !testTo} onClick={() => run(() => testSmtp(testTo), 'Test email sent.')}>
            Send test
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Notify users</CardTitle>
          <CardDescription>Send to all active users (max 500) or leave email empty for all.</CardDescription>
        </CardHeader>
        <CardContent className='space-y-2'>
          <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder='Subject' />
          <textarea
            className='border-input bg-background min-h-[96px] w-full rounded-md border px-3 py-2 text-sm'
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder='Message (HTML allowed)'
          />
          <div className='flex flex-wrap gap-2'>
            <Button disabled={pending || !subject || !message} onClick={() => run(() => sendNotify(subject, message), 'Notification sent.')}>
              Send notification
            </Button>
            <Button variant='outline' disabled={pending} onClick={() => run(() => sendReport(), 'Report sent.')}>
              Send platform report
            </Button>
          </div>
        </CardContent>
      </Card>

      {notice ? <p className='text-sm text-emerald-600'>{notice}</p> : null}
      {error ? <p className='text-destructive text-sm'>{error}</p> : null}
    </div>
  );
}
