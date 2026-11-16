'use server';

import { adminFetch } from '@/lib/clipzi';

export type HostSnapshot = {
  available?: boolean;
  stale?: boolean;
  age_seconds?: number | null;
  latest?: {
    hostname?: string | null;
    cpu?: { percent?: number; cores?: number };
    memory?: { total?: number; used?: number; percent?: number };
    disk?: { total?: number; used?: number; percent?: number };
    load?: { '1'?: number; '5'?: number; '15'?: number };
    uptime_seconds?: number | null;
  } | null;
  services?: {
    key: string;
    label: string;
    container: string;
    found: boolean;
    state: string;
    health: string | null;
    image?: string | null;
    uptime_seconds?: number | null;
    healthy: boolean;
  }[];
  queue?: { queued: number; processing: number };
  workers_active?: number;
  api_uptime_seconds?: number;
  api_version?: string;
};

export type CommandJob = {
  id: string;
  action: string;
  label?: string;
  status: 'pending' | 'running' | 'done' | 'error' | string;
  ok?: boolean | null;
  output?: string;
  created_at?: string;
  finished_at?: string | null;
};

export async function fetchHostSnapshot(): Promise<HostSnapshot | null> {
  try {
    return await adminFetch<HostSnapshot>('/api/admin/system/host');
  } catch {
    return null;
  }
}

/** Antrekan aksi host lalu tunggu hasilnya (maks ~25 detik). */
export async function runSystemAction(action: string): Promise<CommandJob> {
  const created = await adminFetch<{ job: CommandJob }>('/api/admin/system/actions', {
    method: 'POST',
    body: JSON.stringify({ action })
  });
  let job = created.job;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    if (job.status === 'done' || job.status === 'error') return job;
    await new Promise((resolve) => setTimeout(resolve, 2000));
    try {
      job = await adminFetch<CommandJob>(`/api/admin/system/actions/${job.id}`);
    } catch {
      break;
    }
  }
  return job;
}
