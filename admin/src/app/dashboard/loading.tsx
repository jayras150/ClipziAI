import PageContainer from '@/components/layout/page-container';
import { Card, CardContent } from '@/components/ui/card';
import { ClipzySpinner } from '@/components/ui/clipzy-spinner';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Loading state untuk seluruh segmen /dashboard/*.
 *
 * Next.js menampilkan file ini otomatis saat server component sedang mengambil
 * data, jadi admin selalu melihat indikator proses (bukan halaman kosong).
 */
export default function DashboardLoading() {
  return (
    <PageContainer>
      <div className='space-y-4'>
        <div className='flex items-center gap-3'>
          <ClipzySpinner size='md' />
          <div>
            <p className='text-sm font-medium'>Memuat data dashboard…</p>
            <p className='text-muted-foreground text-xs'>Mengambil data terbaru dari API</p>
          </div>
        </div>

        <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-4'>
          {Array.from({ length: 4 }).map((_, index) => (
            <Card key={index}>
              <CardContent className='space-y-3 pt-6'>
                <Skeleton className='h-3 w-24' />
                <Skeleton className='h-7 w-32' />
                <Skeleton className='h-3 w-20' />
              </CardContent>
            </Card>
          ))}
        </div>

        <Card>
          <CardContent className='space-y-3 pt-6'>
            <Skeleton className='h-4 w-40' />
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className='h-9 w-full' />
            ))}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
