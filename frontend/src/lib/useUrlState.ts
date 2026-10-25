import { useCallback } from "react";
import { useSearchParams } from "react-router";

/**
 * Filter state that lives in the URL, so a filtered view can be bookmarked or shared
 * (spec §9.3). Empty values are removed from the URL.
 */
export function useUrlState(): [Record<string, string>, (changes: Record<string, string | null | undefined>, resetPage?: boolean) => void] {
  const [params, setParams] = useSearchParams();
  const state = Object.fromEntries(params.entries());
  const update = useCallback(
    (changes: Record<string, string | null | undefined>, resetPage = true) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(changes)) {
            if (value === null || value === undefined || value === "") next.delete(key);
            else next.set(key, value);
          }
          if (resetPage && !("page" in changes)) next.delete("page");
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  return [state, update];
}
