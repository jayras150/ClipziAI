import { API_URL, getToken } from "@/lib/clipzi";

export const dynamic = "force-dynamic";

export async function GET() {
  const token = await getToken();
  const response = await fetch(API_URL + "/api/admin/settings/proxies/active.txt", {
    headers: { Authorization: "Bearer " + token },
    cache: "no-store"
  });
  const text = await response.text();
  return new Response(text, {
    status: response.ok ? 200 : response.status,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Content-Disposition": "attachment; filename=active-proxies.txt",
      "Cache-Control": "no-store"
    }
  });
}
