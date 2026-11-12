'use client';

import { useFormStatus } from 'react-dom';

import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { ClipzySpinner } from '@/components/ui/clipzy-spinner';
import { Icons } from '@/components/icons';

/**
 * Item dropdown "Log out" yang menampilkan spinner selama server action
 * logout berjalan (tanpa perlu state tambahan di pemanggil).
 */
export function LogoutMenuItem({
  label,
  destructive = false
}: {
  label: string;
  destructive?: boolean;
}) {
  const { pending } = useFormStatus();
  return (
    <DropdownMenuItem
      render={<button type='submit' className='w-full' disabled={pending} />}
      className={destructive ? 'text-destructive' : undefined}
    >
      {pending ? (
        <ClipzySpinner size='xs' variant='ring' className='mr-2' />
      ) : (
        <Icons.logout className='mr-2 h-4 w-4' />
      )}
      {pending ? 'Keluar…' : label}
    </DropdownMenuItem>
  );
}
