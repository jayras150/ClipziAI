import PageContainer from '@/components/layout/page-container';
import { adminFetch } from '@/lib/clipzi';
import SmtpForm, { type SmtpData } from '@/features/settings/components/smtp-form';
import EmailTemplateEditor from '@/features/settings/components/email-template-editor';
import ResendForm from '@/features/settings/components/resend-form';

export const metadata = { title: 'Admin: SMTP' };
export const dynamic = 'force-dynamic';

export default async function SmtpSettingsPage() {
  let data: SmtpData | null = null;
  let error = '';
  try {
    data = await adminFetch<SmtpData>('/api/admin/smtp');
  } catch (exc) {
    error = exc instanceof Error ? exc.message.replace(/^\d{3}\s+/, '') : 'Could not load SMTP settings.';
  }

  return (
    <PageContainer
      pageTitle='SMTP & Email'
      pageDescription='Verification emails, OTP codes, password reset links, user notifications and automatic reports.'
    >
      {error || !data ? (
        <p className='text-destructive text-sm'>{error || 'SMTP settings unavailable.'}</p>
      ) : (
        <div className='space-y-6'>
          <SmtpForm data={data} />
          <ResendForm config={data.config} />
          <EmailTemplateEditor />
        </div>
      )}
    </PageContainer>
  );
}
