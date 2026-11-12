"use server";

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

export async function banUser(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (uid) {
    await adminFetch(`/api/admin/users/${uid}/ban`, { method: 'POST' });
    revalidatePath('/dashboard/users');
  }
}

export async function unbanUser(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  if (uid) {
    await adminFetch(`/api/admin/users/${uid}/unban`, { method: 'POST' });
    revalidatePath('/dashboard/users');
  }
}

export async function adjustCredits(formData: FormData) {
  const uid = String(formData.get('uid') || '');
  const amount = Number(formData.get('amount') || 0);
  if (uid && amount) {
    await adminFetch(`/api/admin/users/${uid}/credits/adjust`, {
      method: 'POST',
      body: JSON.stringify({ amount, reason: 'admin_dashboard' })
    });
    revalidatePath('/dashboard/users');
  }
}
