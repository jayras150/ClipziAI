'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

import { adminFetch } from '@/lib/clipzi';

/**
 * Server actions untuk modul Users.
 *
 * Semua payload dikirim sebagai JSON body (bukan query string) supaya backend
 * tidak menolak dengan 422 seperti versi lama.
 */


/** Pesan error yang bisa dibaca dari ApiError / Error biasa. */
function errorMessage(error: unknown): string {
  if (error && typeof error === 'object') {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) return message;
  }
  return 'Aksi gagal diproses.';
}

/**
 * Bungkus action agar TIDAK PERNAH melempar ke React Server Components.
 *
 * Sebelumnya penolakan backend (mis. `403 Akun admin dilindungi`) membuat RSC
 * gagal render -> halaman global error (React #441). Sekarang kegagalan
 * dikirim sebagai `?err=` dan ditampilkan sebagai banner.
 */
function guard(handler: (formData: FormData) => Promise<void>) {
  return async (formData: FormData): Promise<void> => {
    const uid = String(formData.get('uid') || '');
    const target = uid ? `/dashboard/users/${uid}` : '/dashboard/users';
    try {
      await handler(formData);
    } catch (error) {
      const digest = (error as { digest?: string })?.digest;
      if (typeof digest === 'string' && digest.startsWith('NEXT_REDIRECT')) throw error;
      redirect(`${target}?err=${encodeURIComponent(errorMessage(error))}`);
    }
  };
}

function refreshUserPaths(uid: string) {
  revalidatePath('/dashboard/users');
  revalidatePath(`/dashboard/users/${uid}`);
  revalidatePath('/dashboard/overview');
}

async function banUserImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  const reason = String(formData.get('reason') || 'Pelanggaran ketentuan layanan');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/ban`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
  refreshUserPaths(uid);
}

async function unbanUserImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/unban`, { method: 'POST' });
  refreshUserPaths(uid);
}

async function suspendUserImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  const reason = String(formData.get('reason') || 'Ditangguhkan sementara');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/suspend`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
  refreshUserPaths(uid);
}

async function activateUserImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/activate`, { method: 'POST' });
  refreshUserPaths(uid);
}

async function adjustCreditsImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  const amount = Number(formData.get('amount') || 0);
  const description = String(formData.get('description') || 'Penyesuaian oleh admin');
  if (!uid || !amount) return;
  await adminFetch(`/api/admin/users/${uid}/credits/adjust`, {
    method: 'POST',
    body: JSON.stringify({ amount, description })
  });
  refreshUserPaths(uid);
}

async function setUserPlanImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  const plan = String(formData.get('plan') || 'free');
  const resetCredits = formData.get('reset_credits');
  if (!uid) return;
  const payload: Record<string, unknown> = { plan };
  if (resetCredits !== null && String(resetCredits).trim() !== '') {
    payload.reset_credits = Number(resetCredits);
  }
  await adminFetch(`/api/admin/users/${uid}/plan`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  refreshUserPaths(uid);
}

async function updateUserImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  const name = String(formData.get('name') || '').trim();
  const email = String(formData.get('email') || '').trim();
  const payload: Record<string, unknown> = {};
  if (name) payload.name = name;
  if (email) payload.email = email;
  await adminFetch(`/api/admin/users/${uid}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
  refreshUserPaths(uid);
}

async function forceLogoutUserImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/force-logout`, { method: 'POST' });
  refreshUserPaths(uid);
}

/**
 * Buat password sementara lalu tampilkan sekali di halaman detail
 * (`?temp=...`). Admin harus segera menyalinnya.
 */
async function resetUserPasswordImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  const result = await adminFetch<{ temporary_password?: string }>(
    `/api/admin/users/${uid}/reset-password`,
    { method: 'POST' }
  );
  refreshUserPaths(uid);
  redirect(`/dashboard/users/${uid}?temp=${encodeURIComponent(result?.temporary_password || '')}`);
}

/** Hapus satu user permanen (backend melindungi akun admin). */
async function deleteUserImpl(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}`, { method: 'DELETE' });
  revalidatePath('/dashboard/users');
  revalidatePath('/dashboard/overview');
}

/** Hapus banyak user sekaligus (checkbox). Backend memproses per-id. */
async function bulkDeleteUsersImpl(formData: FormData) {
  const ids = formData.getAll('ids').map((value) => String(value)).filter(Boolean);
  if (!ids.length) return;
  await adminFetch('/api/admin/users/bulk-delete', {
    method: 'POST',
    body: JSON.stringify({ ids })
  });
  revalidatePath('/dashboard/users');
  revalidatePath('/dashboard/overview');
}

export const banUser = guard(banUserImpl);
export const unbanUser = guard(unbanUserImpl);
export const suspendUser = guard(suspendUserImpl);
export const activateUser = guard(activateUserImpl);
export const adjustCredits = guard(adjustCreditsImpl);
export const setUserPlan = guard(setUserPlanImpl);
export const updateUser = guard(updateUserImpl);
export const forceLogoutUser = guard(forceLogoutUserImpl);
export const resetUserPassword = guard(resetUserPasswordImpl);
export const deleteUser = guard(deleteUserImpl);
export const bulkDeleteUsers = guard(bulkDeleteUsersImpl);
