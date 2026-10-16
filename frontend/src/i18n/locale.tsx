/**
 * Two languages, one dictionary shape.
 *
 * The console was written in Chinese, and the platform is used by people who read English --
 * which is not a translation problem but a *shape* problem: every string was a literal inside
 * a component, so there was nowhere to put a second language.
 *
 * Deliberately not `react-i18next` or `i18next`. This codebase hand-rolls its light
 * infrastructure (`useTabParam`, the label maps, the message normalisers) and keeps the
 * kernel dependency-free; what is needed here is a lookup, a hook and a persisted choice,
 * which is about a hundred lines. A framework would add a plugin lifecycle, a loader and a
 * second place for keys to be wrong -- and the test that keeps the two languages in step is
 * worth more than the framework is.
 *
 * Keys are `namespace.name` and each screen owns one namespace file, so a screen's strings
 * live next to nothing else and two people can translate two screens without touching the
 * same file.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { MESSAGES, type Locale, type MessageKey } from './messages';
import { labelIn, type LabelMap } from './labels';

export type { Locale };

const STORAGE_KEY = 'ontology.session.locale';

function readStoredLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'zh' || stored === 'en') return stored;
  } catch {
    // A browser with storage disabled is not a reason to fail to render a page.
  }
  // The product's own language, and the one every existing deployment reads today.
  return 'zh';
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export const LocaleProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [locale, setLocaleState] = useState<Locale>(() => readStoredLocale());

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Remembering the choice is a convenience; failing to remember it is not an error.
    }
  }, []);

  // `<html lang>` is what a screen reader, a translator and the browser's own hyphenation
  // read. Leaving it at `zh` while the interface is English is a small lie with real effects.
  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
  }, [locale]);

  const t = useCallback(
    (key: MessageKey, params?: Record<string, string | number>) => {
      const entry = MESSAGES[key];
      if (!entry) {
        // Visible in the interface on purpose: a key that resolves to nothing should be
        // obvious while it is being written, not silently blank.
        return `⟦${key}⟧`;
      }
      let text: string = entry[locale] ?? entry.zh;
      for (const [name, value] of Object.entries(params ?? {})) {
        text = text.replaceAll(`{${name}}`, String(value));
      }
      return text;
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
};

export function useLocale(): LocaleContextValue {
  const value = useContext(LocaleContext);
  if (!value) {
    throw new Error('useLocale 必须在 LocaleProvider 内使用（LocaleProvider is required above this component）');
  }
  return value;
}

/** The common case: a component that only needs to translate. */
export function useT(): LocaleContextValue['t'] {
  return useLocale().t;
}

/**
 * `label(map, value)` bound to the current language.
 *
 * The enum maps in `i18n/labels.ts` were Chinese-only, so every status chip in the
 * application stayed Chinese in English mode -- the one place a reader looks to see what
 * state something is in. A hook rather than a module-level "current locale": this is a
 * display concern that already has a provider, and a hidden global is how two languages end
 * up on one page.
 */
export function useLabel(): (map: LabelMap, value: unknown) => string {
  const { locale } = useLocale();
  return useCallback((map: LabelMap, value: unknown) => labelIn(map, value, locale), [locale]);
}
