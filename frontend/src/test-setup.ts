/**
 * What jsdom does not implement, and antd needs.
 *
 * Added one at a time, each because a real component failed without it -- not as a general
 * "browser polyfills" file, which grows into a place where failures are hidden. If something
 * needs an entry here, the reason goes beside it.
 */

// antd's responsive observer calls this on mount to decide breakpoints. jsdom has no layout
// engine, so it has no media queries at all; the stub reports every query as not matching,
// which is the smallest-layout answer and the one a table renders correctly under.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// antd's table measures its columns to decide which to collapse. jsdom does no layout, so the
// observer would never fire; the stub exists so the component can register one and render.
// Nothing in these tests depends on a measurement, and anything that did would be a layout
// question -- which belongs to `scripts/ui_smoke.py` in a real browser, not here.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof globalThis.ResizeObserver;
}
