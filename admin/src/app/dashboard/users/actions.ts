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

function refreshUserPaths(uid: string) {
  revalidatePath('/dashboard/users');
  revalidatePath(`/dashboard/users/${uid}`);
  revalidatePath('/dashboard/overview');
}

export async function banUser(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  const reason = String(formData.get('reason') || 'Pelanggaran ketentuan layanan');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/ban`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
  refreshUserPaths(uid);
}

export async function unbanUser(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/unban`, { method: 'POST' });
  refreshUserPaths(uid);
}

export async function suspendUser(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  const reason = String(formData.get('reason') || 'Ditangguhkan sementara');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/suspend`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
  refreshUserPaths(uid);
}

export async function activateUser(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/activate`, { method: 'POST' });
  refreshUserPaths(uid);
}

export async function adjustCredits(formData: FormData) {
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

export async function setUserPlan(formData: FormData) {
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

export async function updateUser(formData: FormData) {
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

export async function forceLogoutUser(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}/force-logout`, { method: 'POST' });
  refreshUserPaths(uid);
}

/**
 * Buat password sementara lalu tampilkan sekali di halaman detail
 * (`?temp=...`). Admin harus segera menyalinnya.
 */
export async function resetUserPassword(formData: FormData) {
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
export async function deleteUser(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (!uid) return;
  await adminFetch(`/api/admin/users/${uid}`, { method: 'DELETE' });
  revalidatePath('/dashboard/users');
  revalidatePath('/dashboard/overview');
}

/** Hapus banyak user sekaligus (checkbox). Backend memproses per-id. */
export async function bulkDeleteUsers(formData: FormData) {
  const ids = formData.getAll('ids').map((value) => String(value)).filter(Boolean);
  if (!ids.length) return;
  await adminFetch('/api/admin/users/bulk-delete', {
    method: 'POST',
    body: JSON.stringify({ ids })
  });
  revalidatePath('/dashboard/users');
  revalidatePath('/dashboard/overview');
}

