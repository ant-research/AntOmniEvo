/**
 * Minimal i18n: a LocaleProvider + useTranslation() hook, with per-language
 * dictionaries living in ./locales/<locale>.ts. To add a language, create a
 * new locale file satisfying `Messages` and register it in DICTS below.
 */
import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { en, type Messages } from './locales/en';
import { zhCN } from './locales/zh-CN';

export type Locale = 'en' | 'zh-CN';

const DICTS: Record<Locale, Messages> = { en, 'zh-CN': zhCN };

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'EN',
  'zh-CN': '中文',
};

const STORAGE_KEY = 'visualizer-locale';

function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'en' || saved === 'zh-CN') return saved;
  } catch {
    // storage unavailable — fall through to browser language
  }
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
}

/** Resolve a dotted key ("detail.avgScore") against a dictionary. */
function resolve(dict: Messages, key: string): string | undefined {
  let cur: unknown = dict;
  for (const part of key.split('.')) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return typeof cur === 'string' ? cur : undefined;
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** Translate a dotted key, interpolating {name} placeholders with vars. */
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [locale, setLocaleState] = useState<Locale>(detectLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // storage unavailable — session-only switch
    }
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      // Fall back to English, then to the raw key, so a missing zh-CN entry
      // never renders blank.
      let s = resolve(DICTS[locale], key) ?? resolve(en, key) ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          s = s.replaceAll(`{${k}}`, String(v));
        }
      }
      return s;
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export function useTranslation(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useTranslation must be used within I18nProvider');
  return ctx;
}

/** Compact toggle button cycling through available locales. */
export const LanguageSwitcher: React.FC = () => {
  const { locale, setLocale } = useTranslation();
  const next: Locale = locale === 'en' ? 'zh-CN' : 'en';
  return (
    <button
      className="lang-switcher"
      onClick={() => setLocale(next)}
      title="Switch language / 切换语言"
    >
      {LOCALE_LABELS[next]}
    </button>
  );
};
