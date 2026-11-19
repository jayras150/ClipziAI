import { NextRequest, NextResponse } from 'next/server';

import { adminFetch, ApiError } from '@/lib/clipzi';

export const dynamic = 'force-dynamic';

/**
 * Antrekan aksi host (clear cache / restart caddy / prune docker).
 *
 * Memakai Route Handler, BUKAN Server Action: URL-nya stabil sehingga tab
 * lama tidak mengirim "Server Action ID" yang sudah mati setelah deploy.
 * Selalu membalas JSON (200) agar UI tidak pernah jatuh ke React #441.
 */
export async function POST(request: NextRequest) {
  try {
    const body = (await request.json().catch(() => ({}))) as { action?: string };
    const action = String(body?.action || '').trim();
    if (!action) {
      return NextResponse.json(
        { ok: false, error: 'Aksi tidak valid.' },
        { headers: { 'Cache-Control': 'no-store' } }
      );
    }
    const created = await adminFetch<{ job: Record<string, unknown> }>(
      '/api/admin/system/actions',
      { method: 'POST', body: JSON.stringify({ action }) }
    );
    return NextResponse.json(
      { ok: true, job: created?.job ?? null },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch (error) {
    const message =
      error instanceof ApiError
        ? error.detail || `HTTP ${error.status}`
        : error instanceof Error
          ? error.message
          : 'Gagal menjalankan aksi.';
    return NextResponse.json(
      { ok: false, error: message },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  }
}
