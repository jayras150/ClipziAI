import { NextResponse } from 'next/server';

import { adminFetch, ApiError } from '@/lib/clipzi';

export const dynamic = 'force-dynamic';

/** Info OS/host (dipakai kartu "Host" di tab System). Stabil, tanpa action ID. */
export async function GET() {
  try {
    const data = await adminFetch<Record<string, unknown>>('/api/admin/system/host-info');
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    const message =
      error instanceof ApiError
        ? error.detail || `HTTP ${error.status}`
        : error instanceof Error
          ? error.message
          : 'Gagal memuat info host.';
    return NextResponse.json(
      { available: false, error: message },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  }
}
