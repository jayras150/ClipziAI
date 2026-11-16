'use client';

import { ReactNode, createContext, useContext, useEffect, useState } from 'react';

import { DEFAULT_THEME } from './theme.config';

const COOKIE_NAME = 'active_theme';
const DESKTOP_KEY = 'clipzi-theme-desktop';
const USER_KEY = 'clipzi-theme-user';
const MOBILE_THEME = 'whatsapp';
const MOBILE_QUERY = '(max-width: 767px)';

function setThemeCookie(theme: string) {
  if (typeof window === 'undefined') return;

  document.cookie = `${COOKIE_NAME}=${theme}; path=/; max-age=31536000; SameSite=Lax; ${window.location.protocol === 'https:' ? 'Secure;' : ''}`;
}

type ThemeContextType = {
  activeTheme: string;
  setActiveTheme: (theme: string) => void;
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ActiveThemeProvider({
  children,
  initialTheme
}: {
  children: ReactNode;
  initialTheme?: string;
}) {
  const themeToUse = initialTheme || DEFAULT_THEME;
  const [activeTheme, setActiveThemeState] = useState<string>(themeToUse);

  // Mobile: default tema WhatsApp (admin tidak bisa membuka pemilih tema di
  // layar kecil). Desktop: pakai tema pilihan admin yang tersimpan.
  useEffect(() => {
    const query = window.matchMedia(MOBILE_QUERY);
    const sync = () => {
      const picked = window.localStorage.getItem(USER_KEY) === '1';
      if (query.matches) {
        if (!picked) setActiveThemeState(MOBILE_THEME);
        return;
      }
      const saved = window.localStorage.getItem(DESKTOP_KEY);
      if (saved) setActiveThemeState(saved);
    };
    sync();
    query.addEventListener('change', sync);
    return () => query.removeEventListener('change', sync);
  }, []);

  const setActiveTheme = (theme: string) => {
    try {
      window.localStorage.setItem(USER_KEY, '1');
      if (!window.matchMedia(MOBILE_QUERY).matches) {
        window.localStorage.setItem(DESKTOP_KEY, theme);
      }
    } catch (_) {
      /* mode private: abaikan */
    }
    setActiveThemeState(theme);
  };

  useEffect(() => {
    // Only update if theme has changed
    const currentTheme = document.documentElement.getAttribute('data-theme');
    if (currentTheme !== activeTheme) {
      setThemeCookie(activeTheme);

      // Remove existing data-theme attribute
      document.documentElement.removeAttribute('data-theme');

      // Remove any theme classes from body (cleanup)
      Array.from(document.body.classList)
        .filter((className) => className.startsWith('theme-'))
        .forEach((className) => {
          document.body.classList.remove(className);
        });

      // Set data-theme on html element
      if (activeTheme) {
        document.documentElement.setAttribute('data-theme', activeTheme);
      }
    } else {
      // Still update cookie in case it's missing
      setThemeCookie(activeTheme);
    }
  }, [activeTheme]);

  return (
    <ThemeContext.Provider value={{ activeTheme, setActiveTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useThemeConfig() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useThemeConfig must be used within an ActiveThemeProvider');
  }
  return context;
}
