import { describe, expect, it, beforeEach, afterEach } from 'vitest';

import { LOCALE_STORAGE_KEY, storedLocale, translateIn, translateNow } from './translate';
import { MESSAGES } from './messages';

/**
 * The lookup, outside React.
 *
 * `i18n/translate.ts` exists because the HTTP client has no provider to call `useT()` from, and
 * the two sentences it needed were hard-coded Chinese -- so in English mode every expired
 * session and every refused action was reported in the other language. The provider and this
 * module share `translateIn`, so what is tested here is also what the screens do.
 */

const realWindow = (globalThis as { window?: unknown }).window;

beforeEach(() => {
  delete (globalThis as { window?: unknown }).window;
});

afterEach(() => {
  (globalThis as { window?: unknown }).window = realWindow;
});

function withStoredLocale(value: string | null): void {
  (globalThis as { window?: unknown }).window = {
    localStorage: { getItem: (key: string) => (key === LOCALE_STORAGE_KEY ? value : null) },
  };
}

describe('storedLocale', () => {
  it('reads the key the provider writes', () => {
    withStoredLocale('en');
    expect(storedLocale()).toBe('en');
    withStoredLocale('zh');
    expect(storedLocale()).toBe('zh');
  });

  it('falls back to the product language when nothing is stored', () => {
    withStoredLocale(null);
    expect(storedLocale()).toBe('zh');
  });

  it('ignores a value that is not a language', () => {
    // Not hypothetical: the key is in localStorage, so anything can be in it.
    withStoredLocale('fr');
    expect(storedLocale()).toBe('zh');
  });

  it('survives a browser with storage disabled', () => {
    (globalThis as { window?: unknown }).window = {
      localStorage: {
        getItem: () => {
          throw new Error('storage is off');
        },
      },
    };
    expect(storedLocale()).toBe('zh');
  });

  it('survives there being no window at all', () => {
    // The SSR pass and the build both import this module without a DOM.
    expect(storedLocale()).toBe('zh');
  });
});

describe('translateIn', () => {
  it('returns the sentence in the language asked for', () => {
    expect(translateIn('en', 'errors.sessionExpired')).toContain('session has expired');
    expect(translateIn('zh', 'errors.sessionExpired')).toContain('登录已失效');
  });

  it('fills placeholders', () => {
    expect(translateIn('en', 'errors.api.ontology_not_found', { ontologyId: '7' })).toContain('7');
    expect(translateIn('zh', 'errors.api.ontology_not_found', { ontologyId: '7' })).toContain('7');
  });

  it('renders a visible sentinel for a key it does not have', () => {
    // The sentinel is load-bearing, not decoration: `codedText` and the HTTP interceptor both
    // decide "do I have a translation for this?" by looking for it, so a blank would silently
    // turn a translated failure into an empty message.
    const missing = translateIn('en', 'errors.api.this_code_does_not_exist' as never);
    expect(missing).toBe('⟦errors.api.this_code_does_not_exist⟧');
  });

  it('leaves a placeholder alone when no fact fills it', () => {
    // Which is the failure the HTTP client checks for before showing it: a fact-name mismatch
    // between the server's template and the dictionary's would otherwise print `{ontologyId}`.
    expect(translateIn('en', 'errors.api.ontology_not_found')).toContain('{ontologyId}');
  });
});

describe('translateNow', () => {
  it('follows the language the provider would be using', () => {
    withStoredLocale('en');
    expect(translateNow('errors.forbidden')).toContain('not allowed');
    withStoredLocale('zh');
    expect(translateNow('errors.forbidden')).toContain('无权');
  });

  it('can name every refusal the platform returns', () => {
    // The dictionary is written by hand and the codes come from the backend; a key that exists
    // in one and not the other is exactly what `tests/test_error_codes.py` fails on. This is the
    // runtime half of the same claim -- that the key is *reachable*, not merely declared.
    const codes = Object.keys(MESSAGES).filter((key) => key.startsWith('errors.api.'));
    expect(codes.length).toBeGreaterThan(50);
    for (const key of codes) {
      expect(translateIn('en', key as never)).not.toContain('⟦');
      expect(translateIn('zh', key as never)).not.toContain('⟦');
    }
  });
});
