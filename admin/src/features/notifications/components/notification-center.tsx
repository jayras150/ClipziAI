'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { Icons } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { NotificationCard } from '@/components/ui/notification-card';
import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import { fetchNotificationLog } from '@/app/dashboard/notifications/actions';
import {
  fetchAdminNotifications,
  markAdminNotificationsRead,
  markAllAdminNotificationsRead,
  type AdminNotification
} from '../actions';

const MAX_VISIBLE = 6;
const POLL_MS = 60_000;

const SEVERITY_LABEL: Record<string, string> = {
  error: 'Error',
  warning: 'Perhatian',
  info: 'Info'
};

export function NotificationCenter() {
  const router = useRouter();
  const [items, setItems] = useState<AdminNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [logLoading, setLogLoading] = useState(false);
  const [logData, setLogData] = useState<LogDialogData | null>(null);

  const load = useCallback(async () => {
    const result = await fetchAdminNotifications();
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError('');
    setItems(result.data.items || []);
    setUnread(result.data.unread_count || 0);
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const markRead = async (key: string) => {
    setItems((prev) => prev.map((item) => (item.key === key ? { ...item, read: true } : item)));
    setUnread((prev) => Math.max(0, prev - 1));
    await markAdminNotificationsRead([key]);
  };

  const markAll = async () => {
    setItems((prev) => prev.map((item) => ({ ...item, read: true })));
    setUnread(0);
    await markAllAdminNotificationsRead();
  };

  const openLog = async (notification: AdminNotification) => {
    setLogOpen(true);
    setLogLoading(true);
    setLogData({
      title: notification.title,
      subtitle: `${notification.severity.toUpperCase()} · ${notification.created_at || ''}`,
      detail: notification.body
    });
    const payload = await fetchNotificationLog(notification.key);
    setLogLoading(false);
    setLogData({
      title: payload.title || notification.title,
      subtitle: `${(payload.severity || notification.severity).toUpperCase()} · ${
        payload.created_at || notification.created_at || ''
      }`,
      detail: payload.detail || notification.body,
      log: payload.log_text || ''
    });
  };

  const visible = items.slice(0, MAX_VISIBLE);

  return (
    <>
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={<Button variant='ghost' size='icon' className='relative h-8 w-8' />}>
        <Icons.notification className='h-4 w-4' />
        {unread > 0 && (
          <span className='bg-destructive text-destructive-foreground absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-medium'>
            {unread > 9 ? '9+' : unread}
          </span>
        )}
        <span className='sr-only'>Notifications</span>
      </PopoverTrigger>
      <PopoverContent align='end' className='w-[calc(100vw-2rem)] p-0 sm:w-[380px]' sideOffset={8}>
        <div className='flex items-center justify-between px-4 pt-3'>
          <Link href='/dashboard/notifications' className='group flex items-center gap-1'>
            <h4 className='text-sm font-semibold group-hover:underline'>Notifications</h4>
            <Icons.chevronRight className='text-muted-foreground h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5' />
          </Link>
          <div className='flex items-center gap-2'>
            {unread > 0 && (
              <span className='bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs'>
                {unread} baru
              </span>
            )}
            {unread > 0 && (
              <Button
                variant='ghost'
                size='sm'
                className='text-muted-foreground h-auto px-2 py-1 text-xs'
                onClick={() => void markAll()}
              >
                Tandai semua
              </Button>
            )}
          </div>
        </div>
        <Separator />
        <ScrollArea className='h-[400px]'>
          {error ? (
            <p className='text-destructive px-4 py-3 text-xs'>{error}</p>
          ) : null}
          {visible.length === 0 ? (
            <div className='flex flex-col items-center justify-center py-12'>
              <Icons.notification className='text-muted-foreground/40 mb-2 h-8 w-8' />
              <p className='text-muted-foreground text-sm'>Belum ada notifikasi</p>
              <p className='text-muted-foreground mt-1 text-xs'>
                Task gagal, worker error, dan masalah runner akan muncul di sini.
              </p>
            </div>
          ) : (
            <div className='flex flex-col gap-1 p-2'>
              {visible.map((notification) => (
                <div key={notification.key} className='space-y-1'>
                <NotificationCard
                  key={notification.key}
                  id={notification.key}
                  title={`[${SEVERITY_LABEL[notification.severity] || notification.severity}] ${
                    notification.title
                  }`}
                  body={notification.body}
                  status={notification.read ? 'read' : 'unread'}
                  createdAt={notification.created_at}
                  actions={[
                    { id: notification.href, label: 'Buka', type: 'redirect', style: 'primary' }
                  ]}
                  onMarkAsRead={(id) => void markRead(id)}
                  onAction={(id, actionId) => {
                    void markRead(id);
                    if (actionId) router.push(actionId);
                  }}
                />
                <div className='flex justify-end'>
                  <Button
                    variant='ghost'
                    size='sm'
                    className='text-muted-foreground h-auto px-2 py-1 text-xs'
                    onClick={() => void openLog(notification)}
                  >
                    Cek Log
                  </Button>
                </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
      <LogDialog open={logOpen} data={logData} loading={logLoading} onClose={() => setLogOpen(false)} />
    </>
  );
}
