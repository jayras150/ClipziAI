import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

const SESSION_COOKIE = "clipzy_session"
const PROTECTED = ["/dashboard", "/profile"]

/**
 * J9 route guard. Token sendiri HttpOnly; middleware hanya membaca flag sesi
 * non-HttpOnly yang ditulis backend saat login/refresh.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  if (!PROTECTED.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) {
    return NextResponse.next()
  }
  if (request.cookies.get(SESSION_COOKIE)?.value === "1") {
    return NextResponse.next()
  }
  const url = request.nextUrl.clone()
  url.pathname = "/login"
  url.search = `?next=${encodeURIComponent(`${pathname}${request.nextUrl.search}`)}`
  return NextResponse.redirect(url)
}

export const config = {
  matcher: ["/dashboard/:path*", "/profile/:path*"]
}
