import { cookies } from 'next/headers';

export const API_URL = process.env.CLIPZI_API_URL || 'http://clipzi-api:8000';
export const TOKEN_COOKIE = 'clipzi_admin_token';
export const REFRESH_COOKIE = 'clipzi_admin_refresh';

/** Error HTTP dari backend, membawa status agar UI bisa membedakan 401/403/404. */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`${status} ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export async function getToken(): Promise<string> {
  const store = await cookies();
  return store.get(TOKEN_COOKIE)?.value ?? '';
}

export async function getRefreshToken(): Promise<string> {
  const store = await cookies();
  return store.get(REFRESH_COOKIE)?.value ?? '';
}

/**
 * Minta access token baru memakai refresh token.
 * Dipakai middleware (menyimpan cookie) dan `adminFetch` (fallback satu request).
 */
export async function refreshAccessToken(
  refreshToken: string
): Promise<{ access_token: string; refresh_token: string } | null> {
  if (!refreshToken) return null;
  try {
    const response = await fetch(`${API_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: 'no-store'
    });
    if (!response.ok) return null;
    const data = (await response.json()) as {
      access_token?: string;
      refresh_token?: string;
    };
    if (!data.access_token) return null;
    return {
      access_token: data.access_token,
      refresh_token: data.refresh_token || refreshToken
    };
  } catch {
    return null;
  }
}

/**
 * Fetch ke backend admin, otomatis memperbarui access token bila 401.
 *
 * Catatan: server component TIDAK boleh menulis cookie, jadi pembaruan yang
 * permanen dilakukan middleware (`src/proxy.ts`). Di sini token baru hanya
 * dipakai untuk request yang sedang berjalan supaya halaman tetap tampil.
 */
export async function adminFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let token = await getToken();

  const doFetch = async (bearer: string) => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(init.headers as Record<string, string> | undefined)
    };
    if (bearer) headers.Authorization = `Bearer ${bearer}`;
    return fetch(`${API_URL}${path}`, { ...init, headers, cache: 'no-store' });
  };

  let response = await doFetch(token);

  if (response.status === 401) {
    const refreshed = await refreshAccessToken(await getRefreshToken());
    if (refreshed) {
      token = refreshed.access_token;
      response = await doFetch(token);
    }
  }

  if (!response.ok) {
    const body = (await response.text()).slice(0, 400);
    let detail = body;
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail || body;
    } catch {
      /* body bukan JSON - pakai apa adanya */
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return null as T;
  const text = await response.text();
  if (!text) return null as T;
  return JSON.parse(text) as T;
}

export type AiProviderMeta = {
  id: string;
  label: string;
  base_url: string;
  default_model: string;
  docs: string;
  needs_base_url: string;
};

export type AiModel = {
  id: string;
  owned_by: string | null;
  context_length: number | null;
};

export type AiConfig = {
  enabled: boolean;
  provider: string;
  base_url: string;
  api_key_set: boolean;
  api_key_masked: string;
  effective_base_url: string | null;
  model_metadata: string;
  model_rerank: string;
  model_regenerate: string;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  max_retries: number;
  rerank_enabled: boolean;
  metadata_enabled: boolean;
  rerank_budget_seconds: number;
  metadata_budget_seconds: number;
  providers: string[];
  /** Alasan AI belum siap dipakai (null = siap). */
  status_hint?: string | null;
  ready?: boolean;
  /** Endpoint & model per kemampuan (satu API key provider). */
  endpoint_chat?: string;
  endpoint_transcribe?: string;
  endpoint_rerank?: string;
  model_transcribe?: string;
  capabilities?: Record<
    string,
    { capability: string; url: string; base_url: string | null; model: string; has_key: boolean; ready: boolean }
  >;
};

export type BrandingConfig = {
  app_name: string;
  tagline: string | null;
  logo_url: string | null;
  favicon_url: string | null;
  /** Favicon per device: icon32 | icon192 | icon512 | apple180 | maskable512 | ico | svg */
  favicons?: Record<string, string | null> | null;
  og_image_url: string | null;
  hero_video_url: string | null;
  accent_color: string;
  support_email: string | null;
  footer_note: string | null;
};

export type PlatformConfig = {
  site_url: string;
  admin_url: string;
  support_email: string;
  timezone: string;
  maintenance_mode: boolean;
  signup_enabled: boolean;
  google_client_id: string;
  pending_domain: string | null;
  pending_admin_domain: string | null;
  applied_domain: string | null;
  domain_status: string;
  domain_requested_at: string | null;
  domain_applied_at: string | null;
  domain_last_error: string | null;
  effective_site_url?: string;
};

export type Paged<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

/** Fetch aman untuk Server Component: tidak pernah throw.
 *
 * Kembalikan { data } bila sukses, atau { error } bila gagal (401/403/404/500,
 * jaringan, JSON rusak, dll). Digunakan untuk halaman yang TIDAK boleh jatuh
 * ke error boundary (React #441) saat backend/agent sedang mati.
 */
export async function adminFetchSafe<T>(
  path: string,
  init: RequestInit = {}
): Promise<{ data: T | null; error: string | null }> {
  try {
    const data = await adminFetch<T>(path, init);
    return { data, error: null };
  } catch (error) {
    if (error instanceof ApiError) {
      let message = error.detail || `HTTP ${error.status}`;
      if (error.status === 401) message = 'Sesi kedaluwarsa. Masuk ulang.';
      if (error.status === 403) message = 'Akses ditolak.';
      if (error.status === 404) message = 'Data tidak ditemukan.';
      return { data: null, error: message };
    }
    return {
      data: null,
      error: error instanceof Error ? error.message : 'Request gagal.'
    };
  }
}
