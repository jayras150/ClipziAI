"use server"

import { revalidatePath } from "next/cache"

import { adminFetch } from "@/lib/clipzi"

function _error(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.replace(/^\d{3}\s+/, "")
  }
  return "Request failed. Try again."
}

export async function fetchSmtp() {
  try {
    const data = await adminFetch<Record<string, unknown>>("/api/admin/smtp")
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}

export async function saveSmtp(payload: Record<string, unknown>) {
  try {
    const data = await adminFetch<Record<string, unknown>>("/api/admin/smtp", {
      method: "PUT",
      body: JSON.stringify(payload),
    })
    revalidatePath("/dashboard/settings/smtp")
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}

export async function testSmtp(to: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>("/api/admin/smtp/test", {
      method: "POST",
      body: JSON.stringify({ to }),
    })
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}

export async function sendNotify(subject: string, message: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>("/api/admin/smtp/notify", {
      method: "POST",
      body: JSON.stringify({ subject, message }),
    })
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}

export async function sendReport() {
  try {
    const data = await adminFetch<Record<string, unknown>>("/api/admin/smtp/report", {
      method: "POST",
      body: JSON.stringify({ emails: [] }),
    })
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}
