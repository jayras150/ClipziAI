import { cn } from '@/lib/utils';

import { ClipzySpinner } from '@/components/ui/clipzy-spinner';

/**
 * Spinner default aplikasi.
 *
 * Dipertahankan dengan API lama (`className`, props svg) supaya komponen
 * template (`LoadingButton`, dsb) otomatis memakai animasi Clipzy yang baru.
 */
function Spinner({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <ClipzySpinner
      variant='ring'
      size='sm'
      aria-label='Memuat'
      className={cn('text-current', className)}
      {...props}
    />
  );
}

export { Spinner };

