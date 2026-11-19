import PageContainer from "@/components/layout/page-container";
import { AdminErrorCard } from "@/components/admin-error-card";
import { StorageManager } from "@/features/settings/components/storage-manager";
import type { StorageConfigView } from "../storage-actions";
import { adminFetchSafe } from "@/lib/clipzi";

export const metadata = { title: "Admin: Storage" };
export const dynamic = "force-dynamic";

export default async function StorageSettingsPage() {
  const configResult = await adminFetchSafe<StorageConfigView>("/api/admin/settings/storage");
  const config = configResult.data;
  const configError = configResult.error;

  if (!config || configError) {
    return (
      <PageContainer pageTitle="Storage">
        <AdminErrorCard
          title="Gagal memuat storage"
          message={configError ?? "Data tidak tersedia."}
        />
      </PageContainer>
    );
  }
  return (
    <PageContainer
      pageTitle="Storage"
      pageDescription="Penyimpanan objek multi-provider: R2, Backblaze B2, S3, Wasabi, dan lainnya"
    >
      <StorageManager initial={config} />
    </PageContainer>
  );
}
