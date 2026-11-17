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


// ---------------------------------------------------------------- templates
export type EmailTemplate = { subject: string; html: string };

export async function fetchEmailTemplates() {
  try {
    const data = await adminFetch<{
      kinds: string[];
      templates: Record<string, EmailTemplate>;
      defaults: Record<string, EmailTemplate>;
      variables: Record<string, string[]>;
    }>("/api/admin/smtp/templates")
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}

export async function saveEmailTemplate(kind: string, subject: string, html: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>("/api/admin/smtp/templates", {
      method: "PUT",
      body: JSON.stringify({ kind, subject, html }),
    })
    revalidatePath("/dashboard/settings/smtp")
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}

export async function resetEmailTemplate(kind: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      `/api/admin/smtp/templates/${kind}/reset`,
      { method: "POST" }
    )
    revalidatePath("/dashboard/settings/smtp")
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}

export async function previewEmailTemplate(kind: string, subject: string, html: string) {
  try {
    const data = await adminFetch<{ subject: string; html: string }>(
      `/api/admin/smtp/templates/${kind}/preview`,
      { method: "POST", body: JSON.stringify({ kind, subject, html }) }
    )
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}

export async function testEmailKind(to: string, kind: string) {
  try {
    const data = await adminFetch<{ subject?: string; sent?: number; log_text?: string }>(
      "/api/admin/smtp/test",
      { method: "POST", body: JSON.stringify({ to, kind }) }
    )
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: _error(error) }
  }
}
