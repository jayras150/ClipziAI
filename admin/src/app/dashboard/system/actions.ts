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
    /** Byte/detik dari agent host (rx/tx rate). */
    network?: {
      rx_bytes?: number;
      tx_bytes?: number;
      rx_rate?: number;
      tx_rate?: number;
      interfaces?: unknown;
    };
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


export type HostInfo = {
  available: boolean;
  name?: string;
  version?: string;
  id?: string;
  kernel?: string;
  arch?: string;
  cores?: number;
  memory_bytes?: number;
  error?: string;
  cached?: boolean;
};

export type SpeedtestResult = {
  ok: boolean;
  down_mbps?: number;
  up_mbps?: number;
  latency_ms?: number;
  taken_at?: string;
  error?: string;
};

export async function fetchHostInfo(): Promise<HostInfo> {
  try {
    return await adminFetch<HostInfo>('/api/admin/system/host-info');
  } catch (error) {
    return {
      available: false,
      error: error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat info host'
    };
  }
}

export async function runSpeedtest(): Promise<SpeedtestResult> {
  try {
    return await adminFetch<SpeedtestResult>('/api/admin/system/speedtest', { method: 'POST' });
  } catch (error) {
    const detail = (error as { detail?: string })?.detail;
    return {
      ok: false,
      error: detail || (error instanceof Error ? error.message : 'Speedtest gagal')
    };
  }
}


export type BackupJob = {
  id: string;
  kind: string;
  status: string;
  archive?: string | null;
  size_bytes?: number | null;
  detail?: string | null;
  created_at?: string | null;
  finished_at?: string | null;
  created_by?: string | null;
};

export type BackupsData = {
  jobs: BackupJob[];
  archives: string[];
  agent_status?: string | null;
  ok?: boolean;
  job?: BackupJob;
  log_text?: string;
  error?: string;
  restart_hint?: string;
};

function _detail(error: unknown): string {
  const detail = (error as { detail?: unknown })?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: string }).message;
    if (message) return message;
  }
  return error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : 'Request gagal.';
}

export async function fetchBackups(): Promise<BackupsData> {
  try {
    return await adminFetch<BackupsData>('/api/admin/system/backups');
  } catch (error) {
    return { jobs: [], archives: [], error: _detail(error) };
  }
}

export async function createBackup(): Promise<BackupsData> {
  try {
    return await adminFetch<BackupsData>('/api/admin/system/backups', { method: 'POST' });
  } catch (error) {
    return { jobs: [], archives: [], error: _detail(error) };
  }
}

export async function restoreBackup(archive: string): Promise<BackupsData> {
  try {
    return await adminFetch<BackupsData>('/api/admin/system/backups/restore', {
      method: 'POST',
      body: JSON.stringify({ archive })
    });
  } catch (error) {
    return { jobs: [], archives: [], error: _detail(error) };
  }
}
