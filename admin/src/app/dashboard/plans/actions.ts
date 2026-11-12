'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

type PlanRow = {
  id: string;
  name: string;
  display_name: Record<string, string>;
  description: Record<string, string>;
  price_monthly: number;
  price_yearly: number;
  credits_monthly: number;
  max_video_duration_minutes: number;
  max_concurrent_tasks: number;
  watermark: boolean;
  priority_queue: boolean;
  youtube_upload: boolean;
  all_editing_features: boolean;
  team_seats: number;
  features_list: string[];
  is_active: boolean;
};

function payloadFrom(formData: FormData) {
  return {
    name: String(formData.get('name') || 'free'),
    display_name: { en: String(formData.get('name') || ''), id: String(formData.get('name') || '') },
    description: { en: '', id: '' },
    price_monthly: Number(formData.get('price_monthly') || 0),
    price_yearly: Number(formData.get('price_yearly') || 0),
    credits_monthly: Number(formData.get('credits_monthly') || 0),
    max_video_duration_minutes: Number(formData.get('max_video_duration_minutes') || 60),
    max_concurrent_tasks: Number(formData.get('max_concurrent_tasks') || 1),
    watermark: formData.get('watermark') === 'on',
    priority_queue: formData.get('priority_queue') === 'on',
    youtube_upload: formData.get('youtube_upload') === 'on',
    all_editing_features: formData.get('all_editing_features') === 'on',
    team_seats: Number(formData.get('team_seats') || 1),
    features_list: String(formData.get('features_list') || '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    is_active: formData.get('is_active') === 'on'
  };
}

export async function createPlan(formData: FormData) {
  await adminFetch('/api/admin/plans/', {
    method: 'POST',
    body: JSON.stringify(payloadFrom(formData))
  });
  revalidatePath('/dashboard/plans');
}

export async function updatePlan(formData: FormData) {
  const id = String(formData.get('id') || '');
  if (!id) return;
  await adminFetch(`/api/admin/plans/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payloadFrom(formData))
  });
  revalidatePath('/dashboard/plans');
}

export async function deletePlan(formData: FormData) {
  const id = String(formData.get('id') || '');
  if (!id) return;
  await adminFetch(`/api/admin/plans/${id}`, { method: 'DELETE' });
  revalidatePath('/dashboard/plans');
}

export type { PlanRow };
