/**
 * Translation without React, for the one layer that has no provider: the HTTP client.
 *
 * Every sentence the console shows comes from `useT()`. The axios interceptor is the
 * exception -- it turns a failed response into the message a caller will show, and it runs
 * outside the component tree, so it cannot call a hook. It used to hard-code its two
 * sentences in Chinese, which meant that in English mode **every expired session and every
 * refused action was reported in the other language**, on the two failures a reader is most
 * likely to meet.
 *
 * This is not the module-level "current locale" that `locale.tsx` argues against. That
 * warning is about *rendering*: a hidden global is how one page ends up in two languages,
 * and the provider already solves it. What is needed here is a one-shot lookup at the
 * moment of failure, and the language is read from the same storage the provider writes to,
 * so a switch and this agree by construction rather than by both being kept in step.
 */

import { MESSAGES, type Locale, type MessageKey } from './messages';

export const LOCALE_STORAGE_KEY = 'ontology.session.locale';

/** The remembered language, or the product's own when nothing is remembered or readable. */
export function storedLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored === 'zh' || stored === 'en') return stored;
  } catch {
    // A browser with storage disabled is not a reason to fail to render an error either.
  }
  return 'zh';
}

/**
 * Look a key up in a given language. The same body as the provider's `t`, kept in one place
 * so the two cannot disagree about what a missing key renders.
 */
export function translateIn(
  locale: Locale,
  key: MessageKey,
  params?: Record<string, string | number>,
): string {
  const entry = MESSAGES[key];
  if (!entry) {
    return `⟦${key}⟧`;
  }
  let text: string = entry[locale] ?? entry.zh;
  for (const [name, value] of Object.entries(params ?? {})) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

/** `translateIn` in whichever language the console is currently in. */
export function translateNow(key: MessageKey, params?: Record<string, string | number>): string {
  return translateIn(storedLocale(), key, params);
}
