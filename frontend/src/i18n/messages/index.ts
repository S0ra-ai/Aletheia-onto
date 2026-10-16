/**
 * Every message, merged from one file per area.
 *
 * A screen adds `./<area>.ts` and one line here. Keeping them apart is what lets two people
 * translate two screens at once without editing the same file -- and it keeps a screen's
 * strings reviewable next to each other instead of scattered through a thousand-line map.
 */

import { shell, type MessageEntry } from './shell';

export type { MessageEntry };

const namespaces = { shell };

/** `'shell.nav.workbench'` style keys, derived from the namespace files. */
export type MessageKey = {
  [N in keyof typeof namespaces]: `${N}.${Extract<keyof (typeof namespaces)[N], string>}`;
}[keyof typeof namespaces];

export const MESSAGES = Object.fromEntries(
  Object.entries(namespaces).flatMap(([namespace, entries]) =>
    Object.entries(entries as Record<string, MessageEntry>).map(([key, entry]) => [`${namespace}.${key}`, entry]),
  ),
) as Record<MessageKey, MessageEntry>;

export type Locale = 'zh' | 'en';
