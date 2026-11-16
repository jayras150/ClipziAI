'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { Icons } from '@/components/icons';
import PageContainer from '@/components/layout/page-container';
import { Button } from '@/components/ui/button';
import { NotificationCard } from '@/components/ui/notification-card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  fetchAdminNotifications,
  markAdminNotificationsRead,
  markAllAdminNotificationsRead,
  type AdminNotification
} from '../actions';

const SEVERITY_LABEL: Record<string, string> = {
  error: 'Error',
  warning: 'Perhatian',
  info: 'Info'
};

export default function NotificationsPage() {
  const router = useRouter();
  const [items, setItems] = useState<AdminNotification[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await fetchAdminNotifications();
    setLoading(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError('');
    setItems(result.data.items || []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const unread = items.filter((item) => !item.read);
  const read = items.filter((item) => item.read);

  const markRead = async (key: string) => {
    setItems((prev) => prev.map((item) => (item.key === key ? { ...item, read: true } : item)));
    await markAdminNotificationsRead([key]);
  };

  const markAll = async () => {
    setItems((prev) => prev.map((item) => ({ ...item, read: true })));
    await markAllAdminNotificationsRead();
  };

  const renderList = (list: AdminNotification[]) => {
    if (loading) {
      return <p className='text-muted-foreground text-sm'>Memuat notifikasi…</p>;
    }
    if (list.length === 0) {
      return (
        <div className='flex flex-col items-center justify-center py-16'>
          <Icons.notification className='text-muted-foreground/40 mb-3 h-10 w-10' />
          <p className='text-muted-foreground text-sm'>Tidak ada notifikasi</p>
        </div>
      );
    }
    return (
      <div className='flex flex-col gap-2'>
        {list.map((item) => (
          <NotificationCard
            key={item.key}
            id={item.key}
            title={`[${SEVERITY_LABEL[item.severity] || item.severity}] ${item.title}`}
            body={item.body}
            status={item.read ? 'read' : 'unread'}
            createdAt={item.created_at}
            actions={[{ id: item.href, label: 'Buka', type: 'redirect', style: 'primary' }]}
            onMarkAsRead={(id) => void markRead(id)}
            onAction={(id, actionId) => {
              void markRead(id);
              if (actionId) router.push(actionId);
            }}
          />
        ))}
      </div>
    );
  };

  return (
    <PageContainer
      pageTitle='Notifications'
      pageDescription='Task gagal, worker Vast error, runner bermasalah, dan env yang belum lengkap.'
      pageHeaderAction={
        items.length > 0 ? (
          <div className='flex gap-2'>
            <Button variant='outline' size='sm' onClick={() => void load()}>
              Muat ulang
            </Button>
            {unread.length > 0 ? (
              <Button variant='secondary' size='sm' onClick={() => void markAll()}>
                Tandai semua dibaca
              </Button>
            ) : null}
          </div>
        ) : undefined
      }
    >
      {error ? <p className='text-destructive mb-3 text-sm'>{error}</p> : null}
      <Tabs defaultValue='all'>
        <TabsList>
          <TabsTrigger value='all'>Semua ({items.length})</TabsTrigger>
          <TabsTrigger value='unread'>Belum dibaca ({unread.length})</TabsTrigger>
          <TabsTrigger value='read'>Sudah dibaca ({read.length})</TabsTrigger>
        </TabsList>
        <TabsContent value='all' className='mt-4'>
          {renderList(items)}
        </TabsContent>
        <TabsContent value='unread' className='mt-4'>
          {renderList(unread)}
        </TabsContent>
        <TabsContent value='read' className='mt-4'>
          {renderList(read)}
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}
