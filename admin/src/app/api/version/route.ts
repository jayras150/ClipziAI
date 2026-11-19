import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

/** ID build admin. Dipakai VersionWatcher untuk reload saat ada deploy baru. */
export async function GET() {
  return NextResponse.json(
    { id: process.env.NEXT_DEPLOYMENT_ID || 'dev' },
    { headers: { 'Cache-Control': 'no-store, max-age=0' } }
  );
}
