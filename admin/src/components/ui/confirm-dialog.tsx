'use client';

import * as React from 'react';
import { AlertDialog as AlertDialogPrimitive } from '@base-ui/react/alert-dialog';
import {
  IconAlertTriangle,
  IconAlertTriangleFilled,
  IconShieldCheck
} from '@tabler/icons-react';

import { Button } from '@/components/ui/button';
import { LoadingButton } from '@/components/ui/loading-button';
import { cn } from '@/lib/utils';

/**
 * Dialog konfirmasi milik aplikasi (pengganti `window.confirm`) supaya aksi
 * destruktif tampil konsisten dengan tema admin: ada ikon tone, ringkasan
 * konteks, spinner saat proses, dan tidak bisa ditutup di tengah proses.
 *
 * Aksesibilitas & UX datang dari Base UI `AlertDialog`: focus trap, Escape,
 * scroll lock, dan `aria-labelledby`/`aria-describedby` otomatis.
 */
export type ConfirmTone = 'danger' | 'warning' | 'neutral';

type ToneStyle = {
  wrap: string;
  icon: React.ReactNode;
  confirmVariant: 'destructive' | 'default';
};

const TONES: Record<ConfirmTone, ToneStyle> = {
  danger: {
    wrap: 'bg-destructive/10 text-destructive ring-destructive/20 dark:bg-destructive/20',
    icon: <IconAlertTriangleFilled />,
    confirmVariant: 'destructive'
  },
  warning: {
    wrap: 'bg-amber-500/10 text-amber-600 ring-amber-500/25 dark:text-amber-400',
    icon: <IconAlertTriangle />,
    confirmVariant: 'default'
  },
  neutral: {
    wrap: 'bg-primary/10 text-primary ring-primary/20',
    icon: <IconShieldCheck />,
    confirmVariant: 'default'
  }
};

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  /** Blok tambahan (mis. detail objek yang akan dihapus). */
  details?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
  /** Ganti ikon default sesuai konteks aksi. */
  icon?: React.ReactNode;
  /** Saat true: tombol disable + spinner, dialog tidak bisa ditutup. */
  loading?: boolean;
  onConfirm: () => void;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  details,
  confirmLabel = 'Lanjutkan',
  cancelLabel = 'Batal',
  tone = 'danger',
  icon,
  loading = false,
  onConfirm
}: ConfirmDialogProps) {
  const style = TONES[tone];

  const requestClose = React.useCallback(() => {
    if (!loading) onOpenChange(false);
  }, [loading, onOpenChange]);

  return (
    <AlertDialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        // Escape/backdrop tidak boleh menutup saat aksi sedang berjalan.
        if (!next && loading) return;
        onOpenChange(next);
      }}
    >
      <AlertDialogPrimitive.Portal>
        <AlertDialogPrimitive.Backdrop
          data-slot='confirm-dialog-overlay'
          className='fixed inset-0 isolate z-50 bg-black/50 duration-150 supports-backdrop-filter:backdrop-blur-sm data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0'
        />
        <AlertDialogPrimitive.Popup
          data-slot='confirm-dialog-content'
          className='fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-xl bg-popover p-5 text-popover-foreground ring-1 ring-foreground/10 shadow-xl outline-none duration-150 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95'
        >
          <div className='flex items-start gap-3'>
            <span
              aria-hidden
              className={cn(
                'mt-0.5 grid size-9 shrink-0 place-items-center rounded-full ring-1 [&_svg]:size-5',
                style.wrap
              )}
            >
              {icon ?? style.icon}
            </span>
            <div className='flex min-w-0 flex-col gap-1.5'>
              <AlertDialogPrimitive.Title className='text-base leading-snug font-semibold tracking-tight'>
                {title}
              </AlertDialogPrimitive.Title>
              {description ? (
                <AlertDialogPrimitive.Description className='text-muted-foreground text-sm leading-relaxed text-pretty'>
                  {description}
                </AlertDialogPrimitive.Description>
              ) : null}
            </div>
          </div>

          {details ? (
            <div className='bg-muted/40 text-muted-foreground rounded-lg border p-3 text-xs leading-relaxed break-words'>
              {details}
            </div>
          ) : null}

          <div className='flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:items-center sm:justify-end'>
            <Button
              type='button'
              variant='outline'
              onClick={requestClose}
              disabled={loading}
              autoFocus
            >
              {cancelLabel}
            </Button>
            <LoadingButton
              type='button'
              variant={style.confirmVariant}
              loading={loading}
              onClick={onConfirm}
            >
              {confirmLabel}
            </LoadingButton>
          </div>
        </AlertDialogPrimitive.Popup>
      </AlertDialogPrimitive.Portal>
    </AlertDialogPrimitive.Root>
  );
}
