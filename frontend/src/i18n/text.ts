/**
 * Text helpers for displaying backend-provided strings.
 */

import type { Locale, MessageKey } from './messages';

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
 *
 * **Two separators, because the two languages punctuate differently.** A finished sentence is
 * followed by nothing in Chinese -- `。` is the gap -- and by a space in English. Joining with
 * an empty string produced 「…before release.Confirm at least the key objects…」 in the English
 * console: two sentences fused at the full stop. An *unfinished* fragment needs a separator in
 * either language, and it differs too: `；` and `; `.
 *
 * The rules live here rather than in the dictionary because they are typography rather than
 * copy: a translator should never be handed the instruction "put a space here", and the message
 * guard rightly refuses an entry whose Chinese side is empty -- which is exactly what this
 * language's sentence gap is.
 */
export const joinSentences = (items: readonly (string | undefined | null)[], locale: Locale): string => {
  const gap = locale === 'zh' ? '' : ' ';
  const separator = locale === 'zh' ? '；' : '; ';
  return items
    .map((item) => (item ?? '').trim())
    .filter(Boolean)
    .map((item, index, all) =>
      index === all.length - 1 ? item : `${item}${/[。；！？!?.;]$/.test(item) ? gap : separator}`,
    )
    .join('');
};

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
        names: unmodelled.join(t('shell.common.listSeparator')),
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

/**
 * What a draft rebuild removed, from the counts the server sends.
 *
 * `discardedSummary` is the server's own sentence, and it is Chinese: interpolating it into a
 * translated sentence produced 「The draft was rebuilt; the previous 9 条规则、32 条映射 was
 * cleared with it」 -- English grammar with Chinese inside it. The counts are structured data,
 * so the console can say the whole thing itself; the server's sentence stays as the fallback
 * for a category this build has no phrase for, which is better than dropping the number.
 */
export const discardedReport = (
  discarded: Record<string, number> | undefined,
  t: Translate,
  fallback = '',
): string => {
  const counted = Object.entries(discarded ?? {}).filter(([, count]) => count > 0);
  if (!counted.length) return fallback;
  return counted
    .map(([category, count]) => {
      // `.one` at exactly one: Chinese has one form, English needs two, and this is the only
      // place the console composes a number into a noun phrase itself.
      const key = count === 1 ? `ontology.discarded.${category}.one` : `ontology.discarded.${category}`;
      const phrase = t(key as MessageKey, { count, category });
      // `t()` renders ⟦key⟧ for a key it does not have; that is the signal to use the
      // server's wording instead of shipping a sentence with braces in it.
      return phrase.startsWith('⟦') ? `${count} ${category}` : phrase;
    })
    .join(t('shell.common.listSeparator'));
};

/**
 * The server's advice, in the reader's language.
 *
 * `nextActions` is a list of sentences the platform computed, and `nextActionCodes` is the
 * same list's identities -- see `backend/ontology_platform/advice.py`, where the two are built
 * from one expression so they cannot drift. A code this build knows is rendered from the
 * dictionary; a code it does not know falls back to that entry's own sentence, which is why
 * the fallback is taken by *index* and not from the payload as a whole.
 *
 * `actions` is tolerated as a plain list of strings, because the payloads that predate the
 * codes still read that way and the console should not render a panel empty for it.
 */
export const adviceTexts = (
  actions: readonly string[] | undefined,
  codes: readonly string[] | undefined,
  t: Translate,
  // The dictionary namespace the codes live in. A parameter rather than a constant because
  // the vocabularies are owned by the screens that show them -- readiness and coverage in
  // `datasource`, the consistency report's advice in `semantic` -- and a helper that guessed
  // would silently fall back to the server's Chinese for every code it guessed wrong.
  namespace = 'datasource',
): string[] =>
  (actions ?? []).map((action, index) => {
    const code = codes?.[index];
    if (!code) return action;
    const translated = t(`${namespace}.advice.${code}` as MessageKey);
    return translated.startsWith('⟦') ? action : translated;
  });

/**
 * The explanation paragraph, composed from the sentences the server named.
 *
 * `explanationParts` carries one `{code, text}` per sentence; `explanation` is the same
 * paragraph joined, for the CLI. The console says each part from its code, and keeps the
 * server's `text` for a code this build does not know. The parts are joined without a
 * separator because each one ends in its own punctuation -- `joinSentences` would add a
 * semicolon between two full stops.
 */
export const explanationParts = (
  parts: readonly { code: string; text: string }[] | undefined,
  t: Translate,
  fallback: string,
): string => {
  if (!parts?.length) return fallback;
  return parts
    .map((part) => {
      const translated = t(`semantic.part.${part.code}` as MessageKey, part as unknown as Record<string, string>);
      return translated.startsWith('⟦') ? part.text : translated;
    })
    .join('');
};

/**
 * A message that counts things, in the form the count asks for.
 *
 * English inflects and Chinese does not, so `<key>.one` is tried first at a count of exactly
 * one and the plain key is the fallback -- which is also what happens for the many counters that
 * have no singular form, because a missing key renders `⟦key⟧` and that is checked for here.
 * 「1 drafts」 and 「1 discussions」 were on the workbench's stat cards before this.
 */
export const countText = (
  key: MessageKey,
  count: number,
  t: Translate,
  params: Record<string, string | number> = {},
): string => {
  if (count === 1) {
    const singular = t(`${key}.one` as MessageKey, { ...params, count });
    if (!singular.startsWith('⟦')) return singular;
  }
  return t(key, { ...params, count });
};
