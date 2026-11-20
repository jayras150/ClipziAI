import { NextResponse } from 'next/server';

import { adminFetch, ApiError } from '@/lib/clipzi';

export const dynamic = 'force-dynamic';

function fail(error: unknown) {
  const detail = (error as { detail?: string })?.detail;
  const message =
    detail ||
    (error instanceof ApiError
      ? error.detail || `HTTP ${error.status}`
      : error instanceof Error
        ? error.message
        : 'Pembersihan server gagal.');
  return NextResponse.json(
    { ok: false, error: message },
    { headers: { 'Cache-Control': 'no-store' } }
  );
}

/** Estimasi sampah server (temp/log/cache/docker) tanpa menghapus. */
export async function GET() {
  try {
    const data = await adminFetch<Record<string, unknown>>('/api/admin/system/cleanup');
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    return fail(error);
  }
}

/**
 * Jalankan pembersihan sampah server.
 * Body: {"dry_run": boolean, "targets": ["temp","logs","cache","docker"]}
 * Default `dry_run=true` sehingga klik pertama hanya menampilkan kandidat.
 */
export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as {
      dry_run?: boolean;
      targets?: string[];
    };
    const data = await adminFetch<Record<string, unknown>>('/api/admin/system/cleanup', {
      method: 'POST',
      body: JSON.stringify({
        dry_run: body.dry_run !== false,
        targets: Array.isArray(body.targets) ? body.targets : undefined
      })
    });
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    return fail(error);
  }
}
