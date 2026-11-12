'use client';

import Link from 'next/link';

import { signOut, signOutEverywhere } from '@/app/auth/actions';
import { Icons } from '@/components/icons';
import { LogoutMenuItem } from '@/components/layout/logout-menu-item';

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar
} from '@/components/ui/sidebar';

export function NavUser({
  user
}: {
  user: {
    name: string;
    email: string;
    avatar: string;
  };
}) {
  const { isMobile } = useSidebar();

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton
                size='lg'
                className='data-popup-open:bg-sidebar-accent data-popup-open:text-sidebar-accent-foreground'
              />
            }
          >
            <Avatar className='h-8 w-8 rounded-lg'>
              <AvatarImage src={user.avatar} alt={user.name} />
              <AvatarFallback className='rounded-lg'>CN</AvatarFallback>
            </Avatar>
            <div className='grid flex-1 text-left text-sm leading-tight'>
              <span className='truncate font-semibold'>{user.name}</span>
              <span className='truncate text-xs'>{user.email}</span>
            </div>
            <Icons.chevronsDown className='ml-auto size-4' />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className='w-(--anchor-width) min-w-56 rounded-lg'
            side={isMobile ? 'bottom' : 'right'}
            align='end'
            sideOffset={4}
          >
            <DropdownMenuGroup>
              <DropdownMenuLabel className='p-0 font-normal'>
                <div className='flex items-center gap-2 px-1 py-1.5 text-left text-sm'>
                  <Avatar className='h-8 w-8 rounded-lg'>
                    <AvatarImage src={user.avatar} alt={user.name} />
                    <AvatarFallback className='rounded-lg'>CN</AvatarFallback>
                  </Avatar>
                  <div className='grid flex-1 text-left text-sm leading-tight'>
                    <span className='truncate font-semibold'>{user.name}</span>
                    <span className='truncate text-xs'>{user.email}</span>
                  </div>
                </div>
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem>
                <Icons.circleCheck className='mr-2 h-4 w-4' />
                <Link href='/dashboard/settings/platform'>Pengaturan Platform</Link>
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Icons.sparkles className='mr-2 h-4 w-4' />
                <Link href='/dashboard/settings/ai'>Pengaturan AI</Link>
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Icons.notification className='mr-2 h-4 w-4' />
                <Link href='/dashboard/notifications'>Alerts</Link>
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              {/* Logout harus benar-benar bekerja: server action menghapus
                  kedua cookie sesi + mencatat audit, lalu redirect ke login. */}
              <form action={signOut}>
                <LogoutMenuItem label='Log out' destructive />
              </form>
              <form action={signOutEverywhere}>
                <LogoutMenuItem label='Log out dari semua perangkat' />
              </form>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
