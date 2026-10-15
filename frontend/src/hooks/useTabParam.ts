import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * Tab state that lives in the URL instead of in component state.
 *
 * Two reasons, and the second one is why this exists at all:
 *
 * A tab is a place. "The audit report" and "the release gate" are screens people refer to
 * each other, and a screen with no address cannot be linked, bookmarked, or pasted into a
 * ticket -- the reader has to be told to click the third tab.
 *
 * And a tab that is not reachable by navigation alone is invisible to
 * `scripts/ui_smoke.py`, which loads a route and reads the DOM. That script is how every
 * empty-column bug in this repository was found: four columns of the model-invocation table
 * and three of the audit log rendered blank for every row while lint, types and tests all
 * passed. A page whose content sits behind a tab is a page that check cannot see.
 *
 * `replace` rather than push: a tab switch is not a place worth a history entry, and a
 * back button that steps through tabs stops being a way out of the page.
 */
export function useTabParam(defaultKey: string, param = 'tab'): [string, (key: string) => void] {
  const [params, setParams] = useSearchParams();
  const current = params.get(param) || defaultKey;

  const setTab = useCallback(
    (key: string) => {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          next.set(param, key);
          return next;
        },
        { replace: true },
      );
    },
    [param, setParams],
  );

  return [current, setTab];
}
