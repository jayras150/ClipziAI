'use client';

import {
  IconBrandAws,
  IconBrandDropbox,
  IconBrandGoogleDrive,
  IconBucket,
  type IconProps
} from '@tabler/icons-react';

/** Logo provider untuk tombol pemilih sumber model Whisper. */
export type ProviderIconKey =
  | 'google-drive'
  | 'dropbox'
  | 'backblaze'
  | 'huggingface'
  | 'aws'
  | 'bucket';

function HuggingFaceLogo({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox='0 0 24 24'
      width={size}
      height={size}
      className={className}
      fill='currentColor'
      aria-hidden='true'
    >
      <path d='M12 1.5c-5.8 0-10.5 4.7-10.5 10.5S6.2 22.5 12 22.5 22.5 17.8 22.5 12 17.8 1.5 12 1.5Zm0 2.1a8.4 8.4 0 0 1 8.4 8.4 8.4 8.4 0 0 1-8.4 8.4A8.4 8.4 0 0 1 3.6 12 8.4 8.4 0 0 1 12 3.6Zm-3.3 4.1c-.6 0-1.1.5-1.1 1.1 0 .4.2.8.6 1-.3.3-.5.7-.5 1.2 0 1 .8 1.8 1.8 1.8.6 0 1.1-.3 1.5-.7l.9.9c.3.3.8.3 1.1 0 .3-.3.3-.8 0-1.1l-.8-.8c.4-.4.6-.9.6-1.4 0-1-.8-1.8-1.8-1.8-.6 0-1.1.3-1.5.7l-.2-.2c.2-.2.3-.4.3-.7 0-.6-.5-1.1-1.1-1.1Zm6.6 0c-.6 0-1.1.5-1.1 1.1 0 .3.1.5.3.7l-.2.2a2 2 0 0 0-1.5-.7c-1 0-1.8.8-1.8 1.8 0 .5.2 1 .6 1.4l-.8.8c-.3.3-.3.8 0 1.1.3.3.8.3 1.1 0l.9-.9c.4.4.9.7 1.5.7 1 0 1.8-.8 1.8-1.8 0-.5-.2-.9-.5-1.2.4-.2.6-.6.6-1 0-.6-.5-1.1-1.1-1.1ZM8.7 11c.4 0 .7.3.7.7s-.3.7-.7.7a.7.7 0 0 1-.7-.7c0-.4.3-.7.7-.7Zm6.6 0c.4 0 .7.3.7.7s-.3.7-.7.7a.7.7 0 0 1-.7-.7c0-.4.3-.7.7-.7Z' />
    </svg>
  );
}

function BackblazeLogo({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox='0 0 24 24'
      width={size}
      height={size}
      className={className}
      fill='currentColor'
      aria-hidden='true'
    >
      <path d='M4.2 3.6h3.1l2.2 8.6 2.3-8.6h2.4l2.3 8.6 2.2-8.6h3.1l-3.7 13.1h-3l-2.1-7.8-2.1 7.8h-3L4.2 3.6Zm-1.5 15h18.6v1.9H2.7v-1.9Z' />
    </svg>
  );
}

export function ProviderLogo({
  icon,
  color,
  size = 20,
  className
}: {
  icon: ProviderIconKey | string;
  color?: string;
  size?: number;
  className?: string;
}) {
  const style = color ? { color } : undefined;
  const common = { size, className, style } as Partial<IconProps>;
  switch (icon) {
    case 'google-drive':
      return <IconBrandGoogleDrive {...common} />;
    case 'dropbox':
      return <IconBrandDropbox {...common} />;
    case 'aws':
      return <IconBrandAws {...common} />;
    case 'huggingface':
      return <HuggingFaceLogo size={size} className={className} />;
    case 'backblaze':
      return <BackblazeLogo size={size} className={className} />;
    default:
      return <IconBucket {...common} />;
  }
}
