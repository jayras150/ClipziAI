'use client';

import { useState, useTransition } from 'react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { loadVastBilling } from '@/app/dashboard/settings/vast/actions';

type BillingData = {
  ok?: boolean;
  error?: string;
  account?: { balance?: number | null; total_spend?: number | null; credit?: number | null };
  summary?: { invoices?: number; charges?: number; credits?: number; net?: number };
  local?: { total_estimated?: number; by_day?: Array<{ date: string; cost: number }> };
  invoices?: Array<{
    timestamp?: string | null;
    type?: string;
    description?: string;
    instance_id?: number | null;
    amount?: number | null;
  }>;
};

function money(value: number | null | undefined) {
  if (value === null || value === undefined) return '-';
  return `$${Math.abs(Number(value)).toFixed(4)}`;
}

export default function VastBillingPanel() {
  const [data, setData] = useState<BillingData | null>(null);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [type, setType] = useState('');
  const [error, setError] = useState('');
  const [pending, startTransition] = useTransition();

  const load = () => {
    setError('');
    startTransition(async () => {
      const result = (await loadVastBilling({ start, end, type })) as BillingData;
      if (result.error) {
        setError(String(result.error));
        return;
      }
      setData(result);
    });
  };

  const exportCsv = () => {
    const rows = data?.invoices || [];
    if (!rows.length) return;
    const header = 'timestamp,type,description,instance_id,amount';
    const lines = rows.map((row) =>
      [
        row.timestamp || '',
        row.type || '',
        `"${(row.description || '').replace(/"/g, '""')}"`,
        row.instance_id ?? '',
        row.amount ?? ''
      ].join(',')
    );
    const blob = new Blob([[header, ...lines].join('\n')], {
      type: 'text/csv;charset=utf-8'
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'vast-invoices.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Billing Vast.ai</CardTitle>
        <CardDescription>
          Saldo, total spend, invoice resmi Vast, dan estimasi biaya lokal dari riwayat instance.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='flex flex-wrap items-end gap-2'>
          <div>
            <label className='text-muted-foreground mb-1 block text-xs'>Dari tanggal</label>
            <Input type='date' value={start} onChange={(event) => setStart(event.target.value)} className='h-9 w-40' />
          </div>
          <div>
            <label className='text-muted-foreground mb-1 block text-xs'>Sampai tanggal</label>
            <Input type='date' value={end} onChange={(event) => setEnd(event.target.value)} className='h-9 w-40' />
          </div>
          <div>
            <label className='text-muted-foreground mb-1 block text-xs'>Tipe</label>
            <select
              value={type}
              onChange={(event) => setType(event.target.value)}
              className='border-input bg-background h-9 rounded-md border px-3 text-sm'
            >
              <option value=''>semua</option>
              <option value='charge'>charge</option>
              <option value='credit'>credit</option>
            </select>
          </div>
          <button
            type='button'
            onClick={load}
            disabled={pending}
            className='bg-primary text-primary-foreground rounded-md px-3 py-2 text-xs disabled:opacity-50'
          >
            {pending ? 'Memuat…' : 'Muat billing'}
          </button>
          {data?.invoices?.length ? (
            <button
              type='button'
              onClick={exportCsv}
              className='hover:bg-muted rounded-md border px-3 py-2 text-xs'
            >
              Export CSV
            </button>
          ) : null}
        </div>
        {data ? (
          <>
            <div className='grid gap-3 text-sm md:grid-cols-4'>
              <div className='rounded-md border p-3'>
                <p className='text-muted-foreground text-xs'>Saldo</p>
                <p className='font-medium'>{money(data.account?.balance)}</p>
              </div>
              <div className='rounded-md border p-3'>
                <p className='text-muted-foreground text-xs'>Total spend</p>
                <p className='font-medium'>{money(data.account?.total_spend)}</p>
              </div>
              <div className='rounded-md border p-3'>
                <p className='text-muted-foreground text-xs'>Charges / credits</p>
                <p className='font-medium'>
                  {money(data.summary?.charges)} / {money(data.summary?.credits)}
                </p>
              </div>
              <div className='rounded-md border p-3'>
                <p className='text-muted-foreground text-xs'>Estimasi lokal</p>
                <p className='font-medium'>{money(data.local?.total_estimated)}</p>
              </div>
            </div>

            <div className='max-h-96 overflow-auto rounded-md border'>
              <table className='w-full text-xs'>
                <thead className='bg-muted/50 text-left'>
                  <tr>
                    <th className='p-2'>Waktu</th>
                    <th className='p-2'>Tipe</th>
                    <th className='p-2'>Deskripsi</th>
                    <th className='p-2'>Instance</th>
                    <th className='p-2 text-right'>Jumlah</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.invoices || []).slice(0, 80).map((row, index) => (
                    <tr key={`${row.timestamp}-${index}`} className='border-t'>
                      <td className='p-2 whitespace-nowrap'>{row.timestamp || '-'}</td>
                      <td className='p-2'>{row.type || '-'}</td>
                      <td className='text-muted-foreground max-w-[360px] truncate p-2'>
                        {row.description || '-'}
                      </td>
                      <td className='p-2'>{row.instance_id ?? '-'}</td>
                      <td className='p-2 text-right'>{money(row.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}

        {error ? <p className='text-destructive text-xs'>{error}</p> : null}
      </CardContent>
    </Card>
  );
}
