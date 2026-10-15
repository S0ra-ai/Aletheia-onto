/**
 * Text helpers for displaying backend-provided strings.
 */

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
