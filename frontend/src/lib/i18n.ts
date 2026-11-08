export const DEFAULT_LOCALE = "id" as const

export const SUPPORTED_LOCALES = [
  "id", "en", "es", "fr", "de", "ja", "ko", "pt", "ru",
  "ar", "hi", "nl", "it", "tr", "vi", "th", "ms",
] as const

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

export function isSupportedLocale(locale: string): locale is SupportedLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(locale)
}

export function getLocaleOrDefault(locale?: string | null): SupportedLocale {
  return locale && isSupportedLocale(locale) ? locale : DEFAULT_LOCALE
}
