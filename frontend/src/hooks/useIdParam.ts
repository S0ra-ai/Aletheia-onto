import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * A selected record that lives in the URL instead of in component state.
 *
 * The same reason `useTabParam` exists, one step further out. A tab is a place; so is "the
 * knowledge base of *this* system". With several ontologies a bare `/admin/knowledge` opens
 * whichever one the page picks by itself, so a link that says "the documents are here" can
 * open a different system's documents than the sender was looking at -- and the reader has
 * no way to tell, because both screens are correct.
 *
 * Absent and non-numeric values are `null` rather than NaN: a URL is user input, and
 * `Number("")` is 0, which would select whichever record happens to carry that id.
 */
export function useIdParam(param: string): [number | null, (id: number) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get(param);
  const parsed = raw === null || raw.trim() === '' ? Number.NaN : Number(raw);
  const current = Number.isInteger(parsed) && parsed > 0 ? parsed : null;

  const select = useCallback(
    (id: number) => {
      setParams(
        previous => {
          const next = new URLSearchParams(previous);
          next.set(param, String(id));
          return next;
        },
        { replace: true },
      );
    },
    [param, setParams],
  );

  return [current, select];
}
