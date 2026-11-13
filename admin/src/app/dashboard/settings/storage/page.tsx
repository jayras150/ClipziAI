import PageContainer from "@/components/layout/page-container";
import { StorageManager } from "@/features/settings/components/storage-manager";
import type { StorageConfigView } from "../storage-actions";
import { adminFetch } from "@/lib/clipzi";

export const metadata = { title: "Admin: Storage" };
export const dynamic = "force-dynamic";

export default async function StorageSettingsPage() {
  const config = await adminFetch<StorageConfigView>("/api/admin/settings/storage");
  return (
    <PageContainer
      pageTitle="Storage"
      pageDescription="Penyimpanan objek multi-provider: R2, Backblaze B2, S3, Wasabi, dan lainnya"
    >
      <StorageManager initial={config} />
    </PageContainer>
  );
}
