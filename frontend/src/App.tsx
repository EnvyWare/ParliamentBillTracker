import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppHeader } from './components/AppHeader';
import { AttributionFooter } from './components/AttributionFooter';
import { BillDetailsSheet } from './components/BillDetailsSheet';
import { BillJourney } from './components/BillJourney';
import { ConcludedBills, SpecialProcedureBills } from './components/BillCollections';
import { DataStatusBanner } from './components/DataStatusBanner';
import { PipelineSkeleton } from './components/PipelineSkeleton';
import { RoutePipeline } from './components/RoutePipeline';
import { SearchAndFilters } from './components/SearchAndFilters';
import { useDebouncedValue } from './hooks/useDebouncedValue';
import { useSnapshot, type UseSnapshotOptions } from './hooks/useSnapshot';
import { useViewState } from './hooks/useViewState';
import { ROUTES } from './model/routes';
import { applyFilters } from './selectors/filters';
import { groupBills } from './selectors/grouping';

const SEARCH_DEBOUNCE_MS = 150;

export interface AppProps {
  /** Injected in tests so no test depends on the real network or clock. */
  readonly snapshotOptions?: UseSnapshotOptions;
  readonly now?: Date;
}

export function App({ snapshotOptions, now }: AppProps = {}): React.JSX.Element {
  const { state, reload } = useSnapshot(snapshotOptions ?? {});
  const { view, setFilters, setSearch, clearFilters, selectBill, closeBill, setBillView } =
    useViewState();

  // The search box stays instant while filtering waits for a pause in typing.
  const [searchInput, setSearchInput] = useState(view.filters.search);
  const debouncedSearch = useDebouncedValue(searchInput, SEARCH_DEBOUNCE_MS);
  const lastFocusedCard = useRef<number | null>(null);

  // Clearing the box applies at once; only typing is debounced. Without this,
  // "Clear all" would leave the previous query filtering for another 150ms and
  // then write it back to the address bar.
  const effectiveSearch = searchInput.trim() === '' ? '' : debouncedSearch;

  // The last search value this component wrote to the address bar. Comparing
  // against it distinguishes "the URL changed because the user typed" from
  // "the URL changed underneath us", which is the only case where the box
  // should be re-seeded. Mirroring unconditionally would let a late effect
  // overwrite characters the user had already typed.
  const lastWrittenSearch = useRef(view.filters.search);

  useEffect(() => {
    if (view.filters.search !== lastWrittenSearch.current) {
      lastWrittenSearch.current = view.filters.search;
      setSearchInput(view.filters.search);
    }
  }, [view.filters.search]);

  useEffect(() => {
    // Only record a settled value, so an in-flight keystroke cannot overwrite
    // a filter change that has already been committed.
    if (effectiveSearch === searchInput && effectiveSearch !== view.filters.search) {
      lastWrittenSearch.current = effectiveSearch;
      setSearch(effectiveSearch);
    }
  }, [effectiveSearch, searchInput, view.filters.search, setSearch]);

  const snapshot = state.status === 'ready' ? state.snapshot : null;

  const filters = useMemo(
    () => ({ ...view.filters, search: effectiveSearch }),
    [view.filters, effectiveSearch],
  );

  const filtered = useMemo(
    () => (snapshot === null ? [] : applyFilters(snapshot.bills, filters)),
    [snapshot, filters],
  );
  const grouped = useMemo(() => groupBills(filtered), [filtered]);

  const selectedBill = useMemo(() => {
    if (snapshot === null || view.selectedBillId === null) return null;
    // Looked up across the whole snapshot, not the filtered set, so a pasted
    // ?bill= link opens even when the current filters would exclude it.
    return snapshot.bills.find((bill) => bill.id === view.selectedBillId) ?? null;
  }, [snapshot, view.selectedBillId]);

  const onSelect = useCallback(
    (billId: number): void => {
      lastFocusedCard.current = billId;
      selectBill(billId);
    },
    [selectBill],
  );

  // Closing the sheet returns focus to the card that opened it, however the
  // sheet was closed: the close button, Escape, or the browser Back button.
  const wasOpen = useRef(false);
  useEffect(() => {
    const isOpen = selectedBill !== null;
    if (wasOpen.current && !isOpen && lastFocusedCard.current !== null) {
      const card = document.getElementById(`bill-card-${lastFocusedCard.current}`);
      card?.focus();
      lastFocusedCard.current = null;
    }
    wasOpen.current = isOpen;
  }, [selectedBill]);

  if (state.status === 'loading') {
    return (
      <div className="app">
        <AppHeader snapshot={null} visibleCount={null} now={now ?? new Date()} />
        <main id="main">
          <PipelineSkeleton />
        </main>
        <AttributionFooter snapshot={null} />
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="app">
        <AppHeader snapshot={null} visibleCount={null} now={now ?? new Date()} />
        <main id="main" className="shell">
          <div className="no-results" role="alert">
            <h2 className="section__title">Bill data could not be loaded</h2>
            <p className="section__intro">{state.message}</p>
            {state.reason !== 'unsupported-schema' && (
              <p style={{ marginTop: '1rem' }}>
                <button type="button" className="button" onClick={reload}>
                  Retry
                </button>
              </p>
            )}
          </div>
        </main>
        <AttributionFooter snapshot={null} />
      </div>
    );
  }

  const nowValue = now ?? new Date();
  const hasResults = filtered.length > 0;
  const showJourney = selectedBill !== null && view.billView === 'journey';

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to the Bill pipeline
      </a>

      <AppHeader snapshot={state.snapshot} visibleCount={filtered.length} now={nowValue} />

      <DataStatusBanner
        snapshot={state.snapshot}
        source={state.source}
        retrievedAt={state.retrievedAt}
        invalidRecords={state.invalidRecords}
        now={nowValue}
      />

      {/* The journey view is about one Bill, so the whole-session controls
          would be noise there. */}
      {!showJourney && (
        <SearchAndFilters
          snapshot={state.snapshot}
          filters={view.filters}
          searchInput={searchInput}
          onSearchChange={setSearchInput}
          onFiltersChange={setFilters}
          onClear={() => {
            setSearchInput('');
            clearFilters();
          }}
        />
      )}

      {/*
        One polite live region for the whole page. Announcing per card as the
        list changes would be unusable; a single result count is what a
        screen-reader user actually needs after changing a filter.
      */}
      {!showJourney && (
        <p className="visually-hidden" role="status" aria-live="polite">
          {filtered.length} {filtered.length === 1 ? 'Bill matches' : 'Bills match'} the current
          filters.
        </p>
      )}

      <main id="main" className={showJourney ? undefined : 'shell'}>
        {showJourney ? (
          <BillJourney bill={selectedBill} onBack={closeBill} />
        ) : (
          <>
            {!hasResults && (
              <div className="no-results">
                <h2 className="section__title">No Bills match these filters</h2>
                <p className="section__intro">
                  The full process is still shown below so you can see where Bills would appear.
                </p>
                <p style={{ marginTop: '1rem' }}>
                  <button
                    type="button"
                    className="button"
                    onClick={() => {
                      setSearchInput('');
                      clearFilters();
                    }}
                  >
                    Reset filters
                  </button>
                </p>
              </div>
            )}

            <div className="routes">
              {ROUTES.map((route) => (
                <RoutePipeline key={route.id} route={route} grouped={grouped} onSelect={onSelect} />
              ))}
            </div>

            <SpecialProcedureBills bills={grouped.special} onSelect={onSelect} />
            <ConcludedBills bills={grouped.concluded} onSelect={onSelect} />
          </>
        )}
      </main>

      <AttributionFooter snapshot={state.snapshot} />

      {selectedBill !== null && !showJourney && (
        <BillDetailsSheet
          bill={selectedBill}
          onClose={closeBill}
          onViewJourney={() => {
            setBillView('journey');
          }}
        />
      )}
    </div>
  );
}
