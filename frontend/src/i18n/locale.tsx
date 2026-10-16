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
import { type Locale, type MessageKey } from './messages';
import { labelIn, type LabelMap } from './labels';
import { LOCALE_STORAGE_KEY as STORAGE_KEY, translateIn } from './translate';

export type { Locale };

/** `?lang=en` wins over the stored choice: see `readStoredLocale`. */
function localeFromUrl(): Locale | null {
  try {
    const requested = new URLSearchParams(window.location.search).get('lang');
    if (requested === 'zh' || requested === 'en') return requested;
  } catch {
    // No `window.location` is not a reason to fail to render a page either.
  }
  return null;
}

/** Remember the link's language and take the parameter back out of the address. */
function adoptUrlLocale(locale: Locale): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Storage may be off; the language still applies to this page view.
  }
  try {
    // This runs while the provider renders, before the router exists -- so the router reads
    // the address without `lang` in it and no later navigation can resurrect it. Left in
    // place, it would outrank the switch on every reload, and a switch that undoes itself is
    // a switch that looks broken.
    const url = new URL(window.location.href);
    url.searchParams.delete('lang');
    window.history.replaceState({}, '', url.toString());
  } catch {
    // A browser that refuses the rewrite keeps the parameter; the language is still right.
  }
}

/**
 * The language to start in: the link, then the remembered choice, then the product's own.
 *
 * `?lang=` first, and deliberately above the stored preference: a stored choice is what the
 * reader set on their own machine, while the URL is what somebody handed them -- "open it in
 * English" has to work for a reader whose console is set to Chinese, or the link is useless
 * for the thing links are for. The link is then adopted as the remembered choice and removed
 * from the address, so the switch still works and the address does not go on claiming a
 * preference the reader has since overruled. It also makes the language reachable without a
 * browser profile, which is what lets `scripts/i18n_audit.py` check the English interface.
 */
function readStoredLocale(): Locale {
  const fromUrl = localeFromUrl();
  if (fromUrl) {
    adoptUrlLocale(fromUrl);
    return fromUrl;
  }
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

  const t = useCallback(
    (key: MessageKey, params?: Record<string, string | number>) => translateIn(locale, key, params),
    [locale],
  );

  // `<html lang>` is what a screen reader, a translator and the browser's own hyphenation
  // read. Leaving it at `zh` while the interface is English is a small lie with real effects.
  //
  // The document title comes along, and it is not decoration: it is the name of the tab, it
  // is what a bookmark and a link preview show, and `index.html` can only ever hold one
  // language -- the one the file was written in. The static title stays as what a browser
  // shows for the moment before the bundle runs.
  //
  // Declared after `t`, not before it: this hook's dependency list is evaluated during the
  // render, so naming `t` above its own `const` is a temporal-dead-zone ReferenceError -- the
  // whole console renders blank, in every language. Reading the title from the dictionary is
  // what the audit found was missing (the sidebar kept its own copy of the Chinese while
  // `shell.app.name` sat in the dictionary unused), and the fix has to respect the order.
  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
    document.title = t('shell.app.name');
  }, [locale, t]);

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
