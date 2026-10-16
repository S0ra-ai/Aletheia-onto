import { describe, expect, it } from 'vitest';

import { codedText, countText, joinSentences } from './text';
import { labelIn, DECISION_STATUS, ONTOLOGY_STATUS, RULE_SEVERITY } from './labels';
import { translateIn } from './translate';
import type { Locale, MessageKey } from './messages';

/**
 * The three helpers the screens compose their sentences with.
 *
 * All three were written because the obvious spelling was wrong in a way nothing caught: a
 * joined list produced `。；`, `t()` on a backend code produced `⟦key⟧` on screen, and an antd
 * column whose map had no entry produced a blank cell.
 */

const translate = (locale: Locale) => (key: MessageKey, params?: Record<string, string | number>) =>
  translateIn(locale, key, params);

describe('codedText', () => {
  const en = translate('en');

  it('says the console sentence when the dictionary has the code', () => {
    const zhsentence = '未发现阻断或风险规则，允许进入后续自动化流程。';
    const said = codedText(en, 'semantic.recommendation.recommendation_blocked', zhsentence);
    expect(said).not.toContain('⟦');
    expect(said).not.toBe(zhsentence);
  });

  it("keeps the server's sentence for a code this build does not know", () => {
    // The whole point of the helper. A newer server, or an extension that declared a new check,
    // sends a sentence the console has no word for -- and the server's own sentence is still
    // true and still readable, which is strictly better than `⟦...⟧`.
    const fromServer = '扩展点新增的检查给出的中文句子。';
    expect(codedText(en, 'datasource.check.brand_new_code.name', fromServer)).toBe(fromServer);
  });

  it('does not mistake a real translation for a miss', () => {
    // The sentinel is a prefix test, so a sentence that merely *contains* a bracket is fine.
    const said = codedText(en, 'errors.api.login_failed', 'fallback');
    expect(said).not.toBe('fallback');
  });
});

describe('joinSentences', () => {
  it('adds no separator where the sentence already ends in one', () => {
    // The defect this exists for: `_next_actions` and `gaps` both return complete sentences, and
    // joining them with `；` produced `……关键字段。；为数据库+API 类传统系统配置……`.
    expect(joinSentences(['第一句。', '第二句。'], 'zh')).toBe('第一句。第二句。');
    expect(joinSentences(['First.', 'Second.'], 'en')).toBe('First. Second.');
  });

  it('separates fragments that carry no punctuation of their own', () => {
    expect(joinSentences(['键', '值'], 'zh')).toBe('键；值');
    expect(joinSentences(['key', 'value'], 'en')).toBe('key; value');
  });

  it('drops empty items rather than leaving a stray separator', () => {
    expect(joinSentences(['only', '', undefined, null], 'en')).toBe('only');
    expect(joinSentences([], 'en')).toBe('');
  });

  it('trims what it joins', () => {
    expect(joinSentences(['  spaced  '], 'en')).toBe('spaced');
  });
});

describe('countText', () => {
  const words: Record<string, string> = { one: '1 段中文', other: '{count} 段中文' };
  let asked: string[] = [];
  const probe = (key: MessageKey): string => {
    asked.push(key);
    return words[key.endsWith('.one') ? 'one' : 'other'] ?? `⟦${key}⟧`;
  };

  it('asks for the singular key at exactly one', () => {
    asked = [];
    countText('governance.finding.x.finding' as MessageKey, 1, probe);
    expect(asked[0]).toBe('governance.finding.x.finding.one');
  });

  it('asks for the plural key at zero and above one', () => {
    for (const count of [0, 2, 11]) {
      asked = [];
      countText('governance.finding.x.finding' as MessageKey, count, probe);
      expect(asked[0]).toBe('governance.finding.x.finding');
    }
  });
});

describe('labelIn', () => {
  it('names a known value in the language asked for', () => {
    expect(labelIn(DECISION_STATUS, 'approved', 'en')).toBeTruthy();
    expect(labelIn(DECISION_STATUS, 'approved', 'zh')).toBeTruthy();
    expect(labelIn(DECISION_STATUS, 'approved', 'en')).not.toBe(labelIn(DECISION_STATUS, 'approved', 'zh'));
  });

  it('falls back to the raw value rather than to nothing', () => {
    // Deliberate: a value this build has no word for is a backend that gained an enum, and
    // English on a Chinese screen is a fault a reader reports, where a blank cell is one they
    // scroll past. `MAP[value]` yields `undefined`, which React renders as nothing at all.
    expect(labelIn(ONTOLOGY_STATUS, 'some_new_status', 'zh')).toBe('some_new_status');
    expect(labelIn(ONTOLOGY_STATUS, undefined, 'zh')).toBe('');
    expect(labelIn(ONTOLOGY_STATUS, null, 'en')).toBe('');
  });

  it('never returns undefined for a value it cannot name', () => {
    // The blank-cell failure in its most literal form.
    for (const value of ['', 'x', 0, false, {}, []]) {
      expect(typeof labelIn(ONTOLOGY_STATUS, value, 'en')).toBe('string');
    }
  });
});

describe('the label maps themselves', () => {
  it('has both languages for every entry', () => {
    // `labelIn` reads `entry[locale] ?? entry.zh`, so an entry with only `zh` silently shows
    // Chinese in English mode -- which is the defect that made every status chip Chinese.
    const empty: string[] = [];
    for (const [name, map] of Object.entries({ DECISION_STATUS, ONTOLOGY_STATUS, RULE_SEVERITY })) {
      for (const [value, entry] of Object.entries(map)) {
        if (!entry.zh?.trim() || !entry.en?.trim()) empty.push(`${name}.${value}`);
      }
    }
    expect(empty).toEqual([]);
  });
});
