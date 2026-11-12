import { cn } from '@/lib/utils';

type SpinnerVariant = 'orbit' | 'ring' | 'dots';
type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

const SIZES: Record<SpinnerSize, string> = {
  xs: 'size-3.5',
  sm: 'size-5',
  md: 'size-7',
  lg: 'size-10',
  xl: 'size-16'
};

const RING_WIDTH: Record<SpinnerSize, string> = {
  xs: '1px',
  sm: '1.5px',
  md: '2px',
  lg: '2.5px',
  xl: '3px'
};

/**
 * Spinner ClipzyAI.
 *
 * - `orbit` (default): dua cincin berputar berlawanan arah + inti berdenyut +
 *   satu titik satelit. Terlihat hidup tanpa gambar/GIF.
 * - `ring`  : cincin conic sederhana (dipakai di dalam tombol).
 * - `dots`  : tiga titik memantul (untuk teks inline).
 *
 * Semua animasi CSS (`cz-*` di globals.css) dan menghormati
 * `prefers-reduced-motion`.
 */
export function ClipzySpinner({
  size = 'md',
  variant = 'orbit',
  className,
  label,
  ...props
}: {
  size?: SpinnerSize;
  variant?: SpinnerVariant;
  className?: string;
  label?: string;
} & React.HTMLAttributes<HTMLSpanElement>) {
  const dimension = SIZES[size];

  if (variant === 'dots') {
    return (
      <span
        role='status'
        aria-label={label || 'Memproses'}
        className={cn('cz-spinner cz-spinner--dots align-middle', className)}
        {...props}
      >
        <span />
        <span />
        <span />
      </span>
    );
  }

  if (variant === 'ring') {
    return (
      <span
        role='status'
        aria-label={label || 'Memproses'}
        className={cn('cz-spinner', dimension, className)}
        style={{ ['--cz-ring-width' as string]: RING_WIDTH[size] }}
        {...props}
      >
        <span className='cz-spinner__ring' />
        <span className='cz-spinner__arc' />
      </span>
    );
  }

  return (
    <span
      role='status'
      aria-label={label || 'Memproses'}
      className={cn('cz-spinner', dimension, className)}
      style={{ ['--cz-ring-width' as string]: RING_WIDTH[size] }}
      {...props}
    >
      <span className='cz-spinner__orbit' />
      <span className='cz-spinner__orbit cz-spinner__orbit--reverse' />
      <span className='cz-spinner__core' />
      <span className='cz-spinner__dot' />
    </span>
  );
}

/** Spinner kecil untuk di dalam teks/tombol. */
export function InlineSpinner({ className }: { className?: string }) {
  return <ClipzySpinner size='xs' variant='ring' className={cn('inline-block', className)} />;
}

/**
 * Baris status proses dengan latar berkilau (shimmer) — dipakai di kartu task,
 * panel worker, atau ringkasan yang sedang berjalan.
 */
export function ProcessingBar({
  title,
  hint,
  progress,
  className
}: {
  title: string;
  hint?: string;
  progress?: number;
  className?: string;
}) {
  return (
    <div className={cn('cz-processing', className)}>
      <ClipzySpinner size='sm' />
      <span className='cz-processing__label'>
        <span className='font-medium'>{title}</span>
        {hint ? <span className='cz-processing__hint'>{hint}</span> : null}
      </span>
      {typeof progress === 'number' ? (
        <span className='ml-auto text-xs font-semibold tabular-nums'>{Math.round(progress)}%</span>
      ) : null}
    </div>
  );
}

/** Loader besar untuk area kosong (tabel/kartu yang sedang dimuat). */
export function OverlayLoader({ label = 'Memuat data…' }: { label?: string }) {
  return (
    <div className='flex min-h-[240px] flex-col items-center justify-center gap-3'>
      <ClipzySpinner size='xl' />
      <p className='text-muted-foreground text-sm'>{label}</p>
    </div>
  );
}
