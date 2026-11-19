import { NextResponse } from 'next/server';

import { adminFetch, ApiError } from '@/lib/clipzi';

export const dynamic = 'force-dynamic';

/** Status job aksi host (dipolling UI tiap 2 detik). Stabil, tanpa action ID. */
export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  try {
    const job = await adminFetch<Record<string, unknown>>(
      `/api/admin/system/actions/${encodeURIComponent(id)}`
    );
    return NextResponse.json(
      { ok: true, job },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch (error) {
    const message =
      error instanceof ApiError
        ? error.detail || `HTTP ${error.status}`
        : error instanceof Error
          ? error.message
          : 'Gagal membaca status aksi.';
    return NextResponse.json(
      { ok: false, error: message },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  }
}
