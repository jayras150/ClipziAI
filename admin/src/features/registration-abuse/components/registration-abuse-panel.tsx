'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import {
  resetDeviceClaim,
  saveDeviceReputationSettings,
  trustDevice
} from '@/app/dashboard/registration-abuse/actions';
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

export type DeviceAccountItem = {
  user_id: string;
  email: string | null;
  name: string;
  created_at: string | null;
  linked_at: string | null;
};

export type DeviceClaimItem = {
  amount: number;
  status: string;
  claimed_at: string | null;
  user_id: string | null;
};

export type DeviceItem = {
  id: string;
  fingerprint_preview: string;
  reputation_score: number;
  reputation_status: string;
  first_seen: string | null;
  last_seen: string | null;
  last_ip_hash: string | null;
  last_user_agent: string | null;
  account_count: number;
  claim_count: number;
  claim: DeviceClaimItem | null;
  accounts: DeviceAccountItem[];
  event_count: number;
};

export type RegistrationAbuseData = {
  items: DeviceItem[];
  total: number;
  page: number;
  page_size: number;
  config: {
    enforce_device_claim: boolean;
    signup_bonus: number;
  };
};

function formatDate(value: string | null): string {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('id-ID', {
      dateStyle: 'medium',
      timeStyle: 'short'
    });
  } catch {
    return value;
  }
}

function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'TRUSTED') return 'secondary';
  if (status === 'HIGH_RISK' || status === 'SUSPICIOUS') return 'destructive';
  if (status === 'LOW_RISK') return 'outline';
  return 'outline';
}

export default function RegistrationAbusePanel({ data }: { data: RegistrationAbuseData }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [enforce, setEnforce] = useState(Boolean(data.config.enforce_device_claim));
  const [bonus, setBonus] = useState(String(data.config.signup_bonus ?? 5));
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const runSave = () => {
    setError('');
    setMessage('');
    startTransition(async () => {
      const response = await saveDeviceReputationSettings({
        enforce_device_claim: enforce,
        signup_bonus: Number(bonus)
      });
      if ('error' in response) {
        setError(String(response.error));
        return;
      }
      setMessage(
        enforce
          ? 'Enforcement aktif: satu perangkat hanya bisa klaim bonus sekali.'
          : 'Shadow mode aktif: semua registrasi tetap mendapat bonus, tetapi device dicatat.'
      );
      router.refresh();
    });
  };

  const runTrust = (device: DeviceItem) => {
    if (!window.confirm(`Tandai device ${device.fingerprint_preview} sebagai TRUSTED?`)) return;
    setError('');
    setMessage('');
    startTransition(async () => {
      const response = await trustDevice(device.id);
      if ('error' in response) {
        setError(String(response.error));
        return;
      }
      setMessage('Device ditandai TRUSTED.');
      router.refresh();
    });
  };

  const runReset = (device: DeviceItem) => {
    if (
      !window.confirm(
        `Reset claim device ${device.fingerprint_preview}? Device bisa klaim bonus lagi.`
      )
    ) {
      return;
    }
    setError('');
    setMessage('');
    startTransition(async () => {
      const response = await resetDeviceClaim(device.id);
      if ('error' in response) {
        setError(String(response.error));
        return;
      }
      setMessage('Claim device direset. Tindakan ini tercatat di audit log.');
      router.refresh();
    });
  };

  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle>Device reputation settings</CardTitle>
          <CardDescription>
            Shadow mode dulu untuk melihat false positive. Aktifkan enforcement setelah data
            registrasi terlihat wajar.
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          <label className='flex items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={enforce}
              onChange={(event) => setEnforce(event.target.checked)}
            />
            Enforce: satu device hanya boleh klaim bonus Free sekali
          </label>
          <div className='flex flex-wrap items-end gap-2'>
            <div className='space-y-1'>
              <label className='text-muted-foreground text-xs'>Bonus signup (kredit)</label>
              <Input
                type='number'
                min={0}
                max={100}
                value={bonus}
                onChange={(event) => setBonus(event.target.value)}
                className='w-28'
              />
            </div>
            <Button type='button' disabled={pending} onClick={runSave}>
              Simpan setelan
            </Button>
            <Badge variant={enforce ? 'destructive' : 'secondary'}>
              {enforce ? 'ENFORCING' : 'SHADOW'}
            </Badge>
          </div>
          {message ? <p className='text-muted-foreground text-sm'>{message}</p> : null}
          {error ? <p className='text-destructive text-sm'>{error}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Devices</CardTitle>
          <CardDescription>
            {data.total} perangkat terdeteksi. Fingerprint ditampilkan sebagian; data mentah tidak
            pernah dikirim ke browser.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {data.items.length === 0 ? (
            <p className='text-muted-foreground text-sm'>
              Belum ada device. Device akan muncul setelah registrasi/login berikutnya.
            </p>
          ) : (
            <div className='overflow-x-auto'>
              <table className='w-full min-w-[980px] text-left text-sm'>
                <thead className='text-muted-foreground border-b text-xs uppercase'>
                  <tr>
                    <th className='py-2 pr-3'>Device</th>
                    <th className='py-2 pr-3'>Status</th>
                    <th className='py-2 pr-3'>Akun</th>
                    <th className='py-2 pr-3'>Free claim</th>
                    <th className='py-2 pr-3'>Terakhir</th>
                    <th className='py-2'>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((device) => (
                    <tr key={device.id} className='border-b align-top last:border-0'>
                      <td className='py-3 pr-3'>
                        <code className='text-xs'>{device.fingerprint_preview}…</code>
                        <div className='text-muted-foreground mt-1 text-xs'>
                          events: {device.event_count}
                        </div>
                      </td>
                      <td className='py-3 pr-3'>
                        <Badge variant={statusVariant(device.reputation_status)}>
                          {device.reputation_status}
                        </Badge>
                        <div className='text-muted-foreground mt-1 text-xs'>
                          risk {device.reputation_score}
                        </div>
                      </td>
                      <td className='py-3 pr-3'>
                        <div className='font-medium'>{device.account_count} akun</div>
                        <div className='text-muted-foreground max-w-xs text-xs'>
                          {device.accounts.map((account) => account.email || account.name).join(', ') ||
                            '—'}
                        </div>
                      </td>
                      <td className='py-3 pr-3'>
                        {device.claim ? (
                          <div>
                            <Badge variant='destructive'>claimed {device.claim.amount}</Badge>
                            <div className='text-muted-foreground mt-1 text-xs'>
                              {formatDate(device.claim.claimed_at)}
                            </div>
                          </div>
                        ) : (
                          <Badge variant='outline'>belum</Badge>
                        )}
                      </td>
                      <td className='text-muted-foreground py-3 pr-3 whitespace-nowrap text-xs'>
                        {formatDate(device.last_seen)}
                        <div className='mt-1 break-all'>
                          ip hash: {device.last_ip_hash ? `${device.last_ip_hash.slice(0, 10)}…` : '—'}
                        </div>
                      </td>
                      <td className='py-3'>
                        <div className='flex flex-wrap gap-2'>
                          <Button
                            type='button'
                            size='sm'
                            variant='outline'
                            disabled={pending || device.reputation_status === 'TRUSTED'}
                            onClick={() => runTrust(device)}
                          >
                            Trust
                          </Button>
                          <Button
                            type='button'
                            size='sm'
                            variant='ghost'
                            disabled={pending || !device.claim}
                            onClick={() => runReset(device)}
                          >
                            Reset claim
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

