import { cookies } from 'next/headers';

export const API_URL = process.env.CLIPZI_API_URL || 'http://clipzi-api:8000';
export const TOKEN_COOKIE = 'clipzi_admin_token';

export async function getToken(): Promise<string> {
  const store = await cookies();
  return store.get(TOKEN_COOKIE)?.value ?? '';
}

export async function adminFetch<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined)
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: 'no-store'
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new Error(`${response.status} ${detail}`);
  }
  return (await response.json()) as T;
}

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
};

export type BrandingConfig = {
  app_name: string;
  tagline: string | null;
  logo_url: string | null;
  favicon_url: string | null;
  og_image_url: string | null;
  accent_color: string;
  support_email: string | null;
  footer_note: string | null;
};
