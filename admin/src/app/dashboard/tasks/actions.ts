'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

export async function cancelTask(formData: FormData) {
  const tid = String(formData.get('tid') || '');
  if (!tid) return;
  await adminFetch(`/api/admin/tasks/${tid}/cancel`, { method: 'POST' });
  revalidatePath('/dashboard/tasks');
  revalidatePath(`/dashboard/tasks/${tid}`);
}

export async function retryTask(formData: FormData) {
  const tid = String(formData.get('tid') || '');
  if (!tid) return;
  await adminFetch(`/api/admin/tasks/${tid}/retry`, { method: 'POST' });
  revalidatePath('/dashboard/tasks');
  revalidatePath(`/dashboard/tasks/${tid}`);
}
