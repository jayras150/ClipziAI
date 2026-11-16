"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

import { hasSession } from "@/lib/auth"

/** CTA "Start free": ke /dashboard bila sudah login, /register bila belum. */
export default function StartFreeLink({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  const [href, setHref] = useState("/register")

  useEffect(() => {
    if (hasSession()) setHref("/dashboard")
  }, [])

  return (
    <Link href={href} className={className}>
      {children}
    </Link>
  )
}
