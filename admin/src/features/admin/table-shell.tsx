import type { ReactNode } from 'react';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';

export type Column = {
  key: string;
  label: string;
  render?: (row: Record<string, unknown>) => ReactNode;
};

type Props = {
  columns: Column[];
  rows: Record<string, unknown>[];
  empty?: string;
};

function defaultCell(value: unknown): ReactNode {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'boolean') return value ? 'ya' : 'tidak';
  if (typeof value === 'object') return JSON.stringify(value).slice(0, 80);
  return String(value);
}

export default function TableShell({ columns, rows, empty }: Props) {
  if (!rows.length) {
    return (
      <p className='text-muted-foreground py-8 text-center text-sm'>
        {empty || 'Belum ada data.'}
      </p>
    );
  }
  return (
    <div className='overflow-x-auto rounded-md border'>
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead key={column.key}>{column.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={String(row.id ?? index)}>
              {columns.map((column) => (
                <TableCell key={column.key} className='whitespace-nowrap text-sm'>
                  {column.render ? column.render(row) : defaultCell(row[column.key])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className='rounded-lg border p-4'>
      <p className='text-muted-foreground text-xs uppercase tracking-wide'>{label}</p>
      <p className='mt-1 text-2xl font-semibold'>{value}</p>
      {hint ? <p className='text-muted-foreground mt-1 text-xs'>{hint}</p> : null}
    </div>
  );
}

export function formatDate(value: unknown): string {
  if (!value) return '-';
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' });
}
