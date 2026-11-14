import { NavGroup } from '@/types';

/** Navigasi admin ClipzyAI (sidebar + command palette). */
export const navGroups: NavGroup[] = [
  {
    label: 'Operasional',
    items: [
      {
        title: 'Overview',
        url: '/dashboard/overview',
        icon: 'dashboard',
        shortcut: ['d', 'd'],
        isActive: false,
        items: []
      },
      {
        title: 'Tasks',
        url: '/dashboard/tasks',
        icon: 'product',
        shortcut: ['t', 't'],
        isActive: false,
        items: []
      },
      {
        title: 'Users',
        url: '/dashboard/users',
        icon: 'teams',
        shortcut: ['u', 'u'],
        isActive: false,
        items: []
      },
      {
        title: 'Workers',
        url: '/dashboard/workers',
        icon: 'sparkles',
        shortcut: ['w', 'w'],
        isActive: false,
        items: []
      }
    ]
  },
  {
    label: 'Billing',
    items: [
      {
        title: 'Transactions',
        url: '/dashboard/transactions',
        icon: 'account',
        shortcut: ['b', 'b'],
        isActive: false,
        items: []
      },
      {
        title: 'Plans',
        url: '/dashboard/plans',
        icon: 'product',
        shortcut: ['p', 'p'],
        isActive: false,
        items: []
      }
    ]
  },
  {
    label: 'Sistem',
    items: [
      {
        title: 'Audit Log',
        url: '/dashboard/audit',
        icon: 'account',
        shortcut: ['a', 'u'],
        isActive: false,
        items: []
      },
      {
        title: 'Alerts',
        url: '/dashboard/notifications',
        icon: 'notification',
        shortcut: ['a', 'l'],
        isActive: false,
        items: []
      },
      {
        title: 'System',
        url: '/dashboard/system',
        icon: 'settings',
        shortcut: ['s', 'y'],
        isActive: false,
        items: []
      }
    ]
  },
  {
    label: 'Settings',
    items: [
      {
        title: 'AI',
        url: '/dashboard/settings/ai',
        icon: 'sparkles',
        shortcut: ['a', 'i'],
        isActive: false,
        items: []
      },
      {
        title: 'Platform',
        url: '/dashboard/settings/platform',
        icon: 'settings',
        shortcut: ['p', 'l'],
        isActive: false,
        items: []
      },
      {
        title: 'YouTube Cookies',
        url: '/dashboard/settings/youtube',
        icon: 'account',
        shortcut: ['y', 'c'],
        isActive: false,
        items: []
      },
      {
        title: 'Storage',
        url: '/dashboard/settings/storage',
        icon: 'billing',
        shortcut: ['s', 't'],
        isActive: false,
        items: []
      },
      {
        title: 'Download Runner',
        url: '/dashboard/settings/runners',
        icon: 'settings',
        shortcut: ['r', 'n'],
        isActive: false,
        items: []
      },
      {
        title: 'Branding',
        url: '/dashboard/settings/branding',
        icon: 'palette',
        shortcut: ['b', 'r'],
        isActive: false,
        items: []
      }
    ]
  }
];
