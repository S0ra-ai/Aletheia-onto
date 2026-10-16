/**
 * Every message, merged from one file per area.
 *
 * A screen adds `./<area>.ts` and one line here. Keeping them apart is what lets two people
 * translate two screens at once without editing the same file -- and it keeps a screen's
 * strings reviewable next to each other instead of scattered through a thousand-line map.
 */

import { shell, type MessageEntry } from './shell';
import { workbench } from './workbench';
import { datasource } from './datasource';
import { ontology } from './ontology';
import { mapping } from './mapping';
import { rules } from './rules';
import { semantic } from './semantic';
import { governance } from './governance';
import { objects } from './objects';
import { knowledge } from './knowledge';
import { feedback } from './feedback';
import { chat } from './chat';
import { graph } from './graph';
import { demo } from './demo';
import { model } from './model';
import { workflow } from './workflow';
import { permission } from './permission';
import { tenancy } from './tenancy';
import { backup } from './backup';
import { errors } from './errors';

export type { MessageEntry };

const namespaces = {
  shell,
  workbench,
  datasource,
  ontology,
  mapping,
  rules,
  semantic,
  governance,
  objects,
  knowledge,
  feedback,
  chat,
  graph,
  demo,
  model,
  workflow,
  permission,
  tenancy,
  backup,
  errors,
};

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
