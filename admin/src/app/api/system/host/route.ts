import { NextResponse } from 'next/server';

import { adminFetch } from '@/lib/clipzi';

export const dynamic = 'force-dynamic';

/**
 * Proxy metrik host untuk komponen client (polling realtime).
 *
 * Token admin hanya ada di cookie httpOnly, jadi browser tidak bisa memanggil
 * backend langsung. Route handler ini menjalankan `adminFetch` di server lalu
 * mengembalikan JSON ke dashboard.
 */
export async function GET() {
  try {
    const data = await adminFetch('/api/admin/system/host');
    return NextResponse.json(data, {
      headers: { 'Cache-Control': 'no-store' }
    });
  } catch (error) {
    return NextResponse.json(
      { available: false, error: (error as Error).message },
      { status: 200, headers: { 'Cache-Control': 'no-store' } }
    );
  }
}
