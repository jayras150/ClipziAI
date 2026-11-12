'use client';

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  XAxis,
  YAxis
} from 'recharts';

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig
} from '@/components/ui/chart';

export type TimelinePoint = {
  date: string;
  tasks: number;
  clips: number;
  signups: number;
  revenue: number;
};

const areaConfig = {
  tasks: { label: 'Task', color: 'var(--chart-1)' },
  clips: { label: 'Klip', color: 'var(--chart-2)' }
} satisfies ChartConfig;

const signupConfig = {
  signups: { label: 'Pendaftar', color: 'var(--chart-3)' }
} satisfies ChartConfig;

const STATUS_COLORS: Record<string, string> = {
  completed: 'var(--chart-2)',
  processing: 'var(--chart-1)',
  queued: 'var(--chart-4)',
  error: 'var(--chart-5)',
  cancelled: 'var(--chart-3)'
};

/** Task & klip per hari (data dari /api/admin/system/metrics). */
export function TasksAreaChart({ data }: { data: TimelinePoint[] }) {
  return (
    <ChartContainer config={areaConfig} className='aspect-auto h-[260px] w-full'>
      <AreaChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray='3 3' />
        <XAxis
          dataKey='date'
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          minTickGap={24}
          tickFormatter={(value: string) => value.slice(5)}
        />
        <YAxis tickLine={false} axisLine={false} width={28} allowDecimals={false} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Area
          dataKey='tasks'
          type='monotone'
          fill='var(--color-tasks)'
          fillOpacity={0.2}
          stroke='var(--color-tasks)'
          strokeWidth={2}
        />
        <Area
          dataKey='clips'
          type='monotone'
          fill='var(--color-clips)'
          fillOpacity={0.2}
          stroke='var(--color-clips)'
          strokeWidth={2}
        />
      </AreaChart>
    </ChartContainer>
  );
}

/** Pendaftar baru per hari. */
export function SignupsBarChart({ data }: { data: TimelinePoint[] }) {
  return (
    <ChartContainer config={signupConfig} className='aspect-auto h-[240px] w-full'>
      <BarChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray='3 3' />
        <XAxis
          dataKey='date'
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          minTickGap={24}
          tickFormatter={(value: string) => value.slice(5)}
        />
        <YAxis tickLine={false} axisLine={false} width={28} allowDecimals={false} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey='signups' fill='var(--color-signups)' radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartContainer>
  );
}

/** Distribusi status task. */
export function StatusPieChart({ data }: { data: { status: string; count: number }[] }) {
  const config = data.reduce<ChartConfig>((acc, item) => {
    acc[item.status] = { label: item.status, color: STATUS_COLORS[item.status] || 'var(--chart-1)' };
    return acc;
  }, {});

  return (
    <ChartContainer config={config} className='mx-auto aspect-square h-[220px]'>
      <PieChart>
        <ChartTooltip content={<ChartTooltipContent nameKey='status' />} />
        <Pie data={data} dataKey='count' nameKey='status' innerRadius={48} strokeWidth={2}>
          {data.map((item) => (
            <Cell key={item.status} fill={STATUS_COLORS[item.status] || 'var(--chart-1)'} />
          ))}
        </Pie>
      </PieChart>
    </ChartContainer>
  );
}
