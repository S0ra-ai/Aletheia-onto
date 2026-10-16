import { defineConfig } from 'vitest/config';

/**
 * A test runner, which this project deliberately did not have.
 *
 * `docs/limitations.md` recorded the absence honestly: eight "this column is blank in every
 * row" defects were found by hand, and the failures that mattered most were covered from
 * outside instead -- `tests/test_frontend_type_agreement.py` holds each screen's fields to what
 * its endpoint sends, and `scripts/ui_smoke.py` reads the drawn rows in a real browser. What
 * that left uncovered is anything that does not change the shape of a rendered table: a wrong
 * fallback, a payload normaliser that silently produces `''`, a key that resolves to nothing.
 * Those are exactly the things that broke, repeatedly, in `api/index.ts`.
 *
 * The reason given for not having one was that it is a dependency decision. It is: every test
 * here runs in `node` with no DOM, so the only thing added is the runner itself -- no jsdom, no
 * Testing Library, no component rendering. What is tested is the layer between the wire and the
 * screens, which is pure by construction and is where the silent failures live.
 *
 * The browser side stays where it was. `scripts/ui_smoke.py` and `scripts/i18n_audit.py` still
 * own "what a reader actually sees", because that question needs a browser and this does not
 * answer it.
 */
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    // The dictionary is read at import time by `i18n/messages/index.ts`; nothing here needs a
    // DOM beyond the `window` a few helpers read, and each test that needs one provides it.
    globals: false,
  },
});
