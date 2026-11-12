'use client';

import { useFormStatus } from 'react-dom';

import { Button } from '@/components/ui/button';
import { ClipzySpinner } from '@/components/ui/clipzy-spinner';
import { cn } from '@/lib/utils';

type SubmitButtonProps = React.ComponentProps<typeof Button> & {
  /** Teks saat proses berjalan (opsional). */
  pendingLabel?: string;
  spinnerSize?: 'xs' | 'sm' | 'md';
  /** Untuk tombol ikon: saat pending hanya tampilkan spinner (tanpa ikon). */
  iconOnly?: boolean;
};

/**
 * Tombol submit yang otomatis menampilkan spinner saat form sedang dikirim.
 *
 * Kenapa: server action (`<form action={...}>`) tidak memberi tahu UI kapan
 * selesai. `useFormStatus()` membaca status form induk, jadi cukup ganti
 * `<Button type='submit'>` menjadi `<SubmitButton>` dan spinner + disable
 * langsung bekerja tanpa menambah state di setiap halaman.
 */
export function SubmitButton({
  children,
  pendingLabel,
  spinnerSize = 'xs',
  iconOnly = false,
  className,
  disabled,
  ...props
}: SubmitButtonProps) {
  const { pending } = useFormStatus();
  return (
    <Button
      type='submit'
      {...props}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={cn('gap-2', className)}
    >
      {pending ? <ClipzySpinner size={spinnerSize} variant='ring' /> : null}
      {pending ? (iconOnly ? null : pendingLabel ?? children) : children}
    </Button>
  );
}
