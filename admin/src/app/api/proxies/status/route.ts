import { NextResponse } from "next/server";

import { proxyFilterStatus } from "@/app/dashboard/settings/proxy-actions";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const status = await proxyFilterStatus();
    return NextResponse.json(status, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json(
      { status: "idle", total: 0, tested: 0, active: 0, dead: 0, error: (error as Error).message },
      { headers: { "Cache-Control": "no-store" } }
    );
  }
}
