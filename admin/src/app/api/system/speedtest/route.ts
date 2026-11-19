import { NextResponse } from 'next/server';

import { adminFetch, ApiError } from '@/lib/clipzi';

export const dynamic = 'force-dynamic';

/** Jalankan speedtest host. Stabil, tanpa Server Action ID. */
export async function POST() {
  try {
    const data = await adminFetch<Record<string, unknown>>('/api/admin/system/speedtest', {
      method: 'POST'
    });
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    const detail = (error as { detail?: string })?.detail;
    const message =
      detail ||
      (error instanceof ApiError
        ? error.detail || `HTTP ${error.status}`
        : error instanceof Error
          ? error.message
          : 'Speedtest gagal.');
    return NextResponse.json(
      { ok: false, error: message },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  }
}
