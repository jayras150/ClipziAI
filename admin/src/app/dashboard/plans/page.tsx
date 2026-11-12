import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { adminFetch } from '@/lib/clipzi';
import { createPlan, deletePlan, updatePlan, type PlanRow } from './actions';

export const metadata = { title: 'Admin: Plans' };
export const dynamic = 'force-dynamic';

function idr(value: number): string {
  return 'Rp ' + new Intl.NumberFormat('id-ID').format(value || 0);
}

function PlanFields({ plan }: { plan?: PlanRow }) {
  return (
    <>
      <div>
        <label className='text-muted-foreground mb-1 block text-xs'>Nama plan</label>
        <select
          name='name'
          defaultValue={plan?.name || 'pro'}
          className='border-input bg-background h-9 rounded-md border px-2 text-sm'
        >
          {['free', 'standar', 'pro', 'team'].map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className='text-muted-foreground mb-1 block text-xs'>Harga/bln</label>
        <Input name='price_monthly' type='number' defaultValue={plan?.price_monthly ?? 0} className='h-9 w-28' />
      </div>
      <div>
        <label className='text-muted-foreground mb-1 block text-xs'>Harga/thn</label>
        <Input name='price_yearly' type='number' defaultValue={plan?.price_yearly ?? 0} className='h-9 w-28' />
      </div>
      <div>
        <label className='text-muted-foreground mb-1 block text-xs'>Kredit/bln</label>
        <Input name='credits_monthly' type='number' defaultValue={plan?.credits_monthly ?? 0} className='h-9 w-24' />
      </div>
      <div>
        <label className='text-muted-foreground mb-1 block text-xs'>Durasi maks</label>
        <Input
          name='max_video_duration_minutes'
          type='number'
          defaultValue={plan?.max_video_duration_minutes ?? 60}
          className='h-9 w-24'
        />
      </div>
      <div>
        <label className='text-muted-foreground mb-1 block text-xs'>Task paralel</label>
        <Input
          name='max_concurrent_tasks'
          type='number'
          defaultValue={plan?.max_concurrent_tasks ?? 1}
          className='h-9 w-20'
        />
      </div>
      <div>
        <label className='text-muted-foreground mb-1 block text-xs'>Kursi tim</label>
        <Input name='team_seats' type='number' defaultValue={plan?.team_seats ?? 1} className='h-9 w-16' />
      </div>
      <div className='flex flex-wrap items-center gap-3 md:col-span-2'>
        <label className='flex items-center gap-1 text-xs'>
          <input type='checkbox' name='watermark' defaultChecked={plan?.watermark ?? true} /> Watermark
        </label>
        <label className='flex items-center gap-1 text-xs'>
          <input type='checkbox' name='priority_queue' defaultChecked={plan?.priority_queue ?? false} />{' '}
          Prioritas
        </label>
        <label className='flex items-center gap-1 text-xs'>
          <input type='checkbox' name='youtube_upload' defaultChecked={plan?.youtube_upload ?? false} />{' '}
          YouTube
        </label>
        <label className='flex items-center gap-1 text-xs'>
          <input
            type='checkbox'
            name='all_editing_features'
            defaultChecked={plan?.all_editing_features ?? false}
          />{' '}
          Semua editing
        </label>
        <label className='flex items-center gap-1 text-xs'>
          <input type='checkbox' name='is_active' defaultChecked={plan?.is_active ?? true} /> Aktif
        </label>
      </div>
      <div className='md:col-span-2'>
        <label className='text-muted-foreground mb-1 block text-xs'>Fitur (pisahkan koma)</label>
        <Input name='features_list' defaultValue={(plan?.features_list || []).join(', ')} className='h-9' />
      </div>
    </>
  );
}

export default async function PlansPage() {
  const plans = await adminFetch<PlanRow[]>('/api/admin/plans/');

  return (
    <PageContainer pageTitle='Plans' pageDescription={`${plans.length} plan terdaftar`}>
      <div className='space-y-4'>
        <Card>
          <CardHeader>
            <CardTitle>Plan tersedia</CardTitle>
            <CardDescription>
              Ubah harga/kredit lalu simpan. Halaman pricing publik membaca data ini.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-4'>
            {plans.length ? (
              plans.map((plan) => (
                <form key={plan.id} action={updatePlan} className='grid gap-2 border-b pb-4 md:grid-cols-2'>
                  <input type='hidden' name='id' value={plan.id} />
                  <div className='flex items-center gap-2 md:col-span-2'>
                    <Badge variant={plan.is_active ? 'secondary' : 'outline'}>{plan.name}</Badge>
                    <span className='text-muted-foreground text-xs'>
                      {idr(plan.price_monthly)}/bln · {plan.credits_monthly} kredit
                    </span>
                  </div>
                  <PlanFields plan={plan} />
                  <div className='md:col-span-2'>
                    <Button size='sm' type='submit'>
                      Simpan
                    </Button>
                  </div>
                </form>
              ))
            ) : (
              <p className='text-muted-foreground text-sm'>
                Belum ada plan. Tambahkan lewat form di bawah (atau jalankan seed).
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Tambah / timpa plan</CardTitle>
            <CardDescription>
              Nama plan harus salah satu: free, standar, pro, team. Bila sudah ada, datanya ditimpa.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form action={createPlan} className='grid gap-2 md:grid-cols-2'>
              <PlanFields />
              <div className='md:col-span-2'>
                <Button size='sm' type='submit'>
                  Simpan plan
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Hapus plan</CardTitle>
            <CardDescription>
              Plan yang masih dipakai user sebaiknya dinonaktifkan, bukan dihapus.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Plan</TableHead>
                  <TableHead>Harga</TableHead>
                  <TableHead>Kredit</TableHead>
                  <TableHead className='text-right'>Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {plans.map((plan) => (
                  <TableRow key={plan.id}>
                    <TableCell className='text-xs font-medium'>{plan.name}</TableCell>
                    <TableCell className='text-xs'>{idr(plan.price_monthly)}</TableCell>
                    <TableCell className='text-xs'>{plan.credits_monthly}</TableCell>
                    <TableCell className='text-right'>
                      <form action={deletePlan}>
                        <input type='hidden' name='id' value={plan.id} />
                        <Button size='sm' type='submit' variant='destructive'>
                          Hapus
                        </Button>
                      </form>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
