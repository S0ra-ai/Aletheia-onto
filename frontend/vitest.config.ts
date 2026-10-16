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
 * The reason given for not having one was that it is a dependency decision. It is, and it was
 * taken twice: first the runner alone, in `node` with no DOM, for the pure layer between the wire
 * and the screens. Then jsdom and Testing Library, for the one class of defect that keeps
 * arriving there and nowhere else.
 *
 * **Every "this column is blank in every row" defect was this shape.** antd draws nothing for a
 * `dataIndex` that is not in the row, so a screen whose type says `ruleType` and whose endpoint
 * sends `rule_type` renders an empty cell -- and the types check out, the linter sees a valid
 * string, and the request succeeded. Seven of them were found by hand over this project's life,
 * one at a time, on the days somebody happened to open the right page; `scripts/ui_smoke.py`
 * reports them now, but it needs a browser and a live instance, which is why it is a diagnostic
 * run by whoever remembers rather than a gate on every change.
 *
 * `src/components/TableColumns.test.tsx` renders the real components with rows and asserts the
 * cells have text. It asks for the DOM with a `@vitest-environment jsdom` directive at the top
 * of the file, so the default stays `node`: a pure test under jsdom is a slower pure test.
 *
 * `scripts/ui_smoke.py` and `scripts/i18n_audit.py` still own what only a real browser can
 * answer -- a page that fails to mount, a route that renders the wrong application, the whole
 * sweep in one pass. This covers the cells.
 */
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    setupFiles: ['src/test-setup.ts'],
    // The dictionary is read at import time by `i18n/messages/index.ts`; nothing here needs a
    // DOM beyond the `window` a few helpers read, and each test that needs one provides it.
    globals: false,
  },
});
