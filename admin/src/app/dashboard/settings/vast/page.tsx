import { redirect } from 'next/navigation';

// Halaman lama digabung ke "Instance" agar bookmark tetap bekerja.
export const dynamic = 'force-dynamic';

export default function LegacySettingsRedirect() {
  redirect('/dashboard/settings/instance');
}
