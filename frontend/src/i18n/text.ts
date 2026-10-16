/**
 * Text helpers for displaying backend-provided strings.
 */

import type { MessageKey } from './messages';

/**
 * The translate function, as a parameter.
 *
 * These helpers build sentences, and a sentence belongs to a language. Keeping them pure and
 * passing `t` in -- rather than reaching for a module-level current locale -- is what let the
 * two of them stop being Chinese-only text that the bilingual interface carried unchanged.
 */
type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;

/**
 * Join sentences that may already end in their own punctuation.
 *
 * Every list this is used for arrives from the backend as complete sentences that end with
 * `。` -- `_next_actions` and `gaps` both build them that way. Joining those with `；`
 * produced `……关键字段。；为数据库+API 或 API 类传统系统配置……` in the readiness panel and in
 * five other places: a full stop immediately followed by a semicolon, which reads as a typo
 * because it is one.
 *
 * A separator is added only where the sentence does not already carry one, so a list of
 * punctuated sentences comes out as prose and a list of bare fragments still gets separated.
 * The backend has the same rule for the same reason
 * (`knowledge_documents._looks_like_complete_sentence`), which is where the pattern came
 * from.
 */
export const joinSentences = (items: readonly (string | undefined | null)[]): string =>
  items
    .map((item) => (item ?? '').trim())
    .filter(Boolean)
    .map((item, index, all) => (index < all.length - 1 && !/[。；！？!?.;]$/.test(item) ? `${item}；` : item))
    .join('');

/**
 * What to say after a scan, in one place because two screens scan and they drifted.
 *
 * The scan keeps the draft derived from the source instead of rebuilding it -- that is what
 * stopped a re-scan from deleting rules and workflows -- so a source that gained a table
 * keeps a model that has never seen it. 「扫描完成」 was printed for that case and for the one
 * where nothing changed: a report that reads the same for "all is well" and "the model is now
 * out of date" is not a report.
 *
 * `warning` rather than `success` when the model is behind, because the reader has a decision
 * to make: take the new tables in (which clears the draft's rules, mappings and workflows) or
 * leave them out.
 */
export const scanReport = (
  result: { tables?: unknown[]; modelledOntologyId?: number | null; unmodelledTables?: string[] } | undefined,
  t: Translate,
): { level: 'success' | 'warning'; text: string } => {
  const tables = result?.tables?.length ?? 0;
  const unmodelled = result?.unmodelledTables ?? [];
  if (result?.modelledOntologyId && unmodelled.length) {
    return {
      level: 'warning',
      text: t('datasource.scanReportBehind', {
        tables,
        missing: unmodelled.length,
        // The list separator is punctuation, and punctuation is part of the language: the
        // English sentence needs `, ` where the Chinese one takes `、`.
        names: unmodelled.join(t('datasource.listSeparator')),
      }),
    };
  }
  return { level: 'success', text: t('datasource.scanReportOk', { tables }) };
};

/** The same treatment for initialising a knowledge base: say what it produced. */
export const initializeReport = (
  name: string,
  result: { scan?: { tables?: number }; reasoningChain?: { objects?: unknown[] } } | undefined,
  t: Translate,
): string => {
  const tables = result?.scan?.tables ?? 0;
  const objects = result?.reasoningChain?.objects?.length ?? 0;
  return t('datasource.initializeReport', { name, tables, objects });
};
