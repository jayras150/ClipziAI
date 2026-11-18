'use server';

import { adminFetch } from '@/lib/clipzi';

export type WorkerLogLine = {
  id: string;
  task_id: string | null;
  instance_id: number | null;
  seq: number;
  level: string;
  stage: string | null;
  message: string;
  created_at: string | null;
};

export async function fetchWorkerLines(
  taskId: string,
  afterSeq = 0,
  level = ''
): Promise<{ items: WorkerLogLine[]; error?: string }> {
  const query = new URLSearchParams({ task_id: taskId, after_seq: String(afterSeq), limit: '300' });
  if (level) query.set('level', level);
  try {
    const data = await adminFetch<{ items: WorkerLogLine[]; error?: string | null }>(
      `/api/admin/workers/lines?${query.toString()}`
    );
    return { items: data.items || [], error: data.error || undefined };
  } catch (error) {
    return {
      items: [],
      error: error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat log worker.'
    };
  }
}


export type WorkerTaskRow = {
  id: string;
  status: string | null;
  progress: number | null;
  download_status: string | null;
  error_message: string | null;
  created_at: string | null;
  log_count: number;
};

export async function fetchWorkerTasks(limit = 30): Promise<{
  items: WorkerTaskRow[];
  error?: string;
}> {
  try {
    const data = await adminFetch<{ items: WorkerTaskRow[]; error?: string | null }>(
      `/api/admin/workers/tasks?limit=${limit}`
    );
    return { items: data.items || [], error: data.error || undefined };
  } catch (error) {
    return {
      items: [],
      error: error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat task.'
    };
  }
}
