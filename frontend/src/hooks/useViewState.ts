/**
 * Filters and the selected Bill, kept in the address bar.
 *
 * Discrete choices push a history entry so Back restores the previous view.
 * Typing in the search box replaces instead, because one history entry per
 * keystroke would make Back useless.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { DEFAULT_FILTERS, type FilterState } from '../selectors/filters';
import { parseViewState, viewUrl, type BillView, type ViewState } from '../selectors/urlState';

export type CommitMode = 'push' | 'replace';

export interface UseViewStateResult {
  readonly view: ViewState;
  readonly setFilters: (filters: FilterState, mode?: CommitMode) => void;
  readonly setSearch: (search: string) => void;
  readonly clearFilters: () => void;
  readonly selectBill: (billId: number, billView?: BillView) => void;
  readonly closeBill: () => void;
  /** Switch between the summary sheet and the full journey view. */
  readonly setBillView: (billView: BillView) => void;
}

function currentView(): ViewState {
  return parseViewState(window.location.search);
}

export function useViewState(): UseViewStateResult {
  const [view, setView] = useState<ViewState>(currentView);
  /** Depth of history entries this component pushed for an open Bill. */
  const pushedBillEntries = useRef(0);

  useEffect(() => {
    const onPopState = (): void => {
      pushedBillEntries.current = Math.max(0, pushedBillEntries.current - 1);
      setView(currentView());
    };
    window.addEventListener('popstate', onPopState);
    return () => {
      window.removeEventListener('popstate', onPopState);
    };
  }, []);

  const commit = useCallback((next: ViewState, mode: CommitMode): void => {
    const url = viewUrl(next, window.location.pathname);
    if (mode === 'push') {
      window.history.pushState(null, '', url);
    } else {
      window.history.replaceState(null, '', url);
    }
    setView(next);
  }, []);

  const setFilters = useCallback(
    (filters: FilterState, mode: CommitMode = 'push'): void => {
      // Changing a filter while a Bill is open closes it: the open Bill may
      // no longer be in the result set.
      commit({ filters, selectedBillId: null, billView: 'summary' }, mode);
    },
    [commit],
  );

  const setSearch = useCallback((search: string): void => {
    setView((previous) => {
      const next: ViewState = {
        filters: { ...previous.filters, search },
        selectedBillId: previous.selectedBillId,
        billView: previous.billView,
      };
      window.history.replaceState(null, '', viewUrl(next, window.location.pathname));
      return next;
    });
  }, []);

  const clearFilters = useCallback((): void => {
    commit({ filters: DEFAULT_FILTERS, selectedBillId: null, billView: 'summary' }, 'push');
  }, [commit]);

  const selectBill = useCallback((billId: number, billView: BillView = 'summary'): void => {
    setView((previous) => {
      const next: ViewState = { filters: previous.filters, selectedBillId: billId, billView };
      window.history.pushState(null, '', viewUrl(next, window.location.pathname));
      pushedBillEntries.current += 1;
      return next;
    });
  }, []);

  const setBillView = useCallback((billView: BillView): void => {
    setView((previous) => {
      const next: ViewState = { ...previous, billView };
      window.history.pushState(null, '', viewUrl(next, window.location.pathname));
      pushedBillEntries.current += 1;
      return next;
    });
  }, []);

  const closeBill = useCallback((): void => {
    // Going back keeps the history stack honest, so Back and the close button
    // leave the user in the same place. A Bill opened from a pasted URL was
    // never pushed by this component, so that case replaces instead.
    if (pushedBillEntries.current > 0) {
      window.history.back();
      return;
    }
    setView((previous) => {
      const next: ViewState = {
        filters: previous.filters,
        selectedBillId: null,
        billView: 'summary',
      };
      window.history.replaceState(null, '', viewUrl(next, window.location.pathname));
      return next;
    });
  }, []);

  return { view, setFilters, setSearch, clearFilters, selectBill, closeBill, setBillView };
}
