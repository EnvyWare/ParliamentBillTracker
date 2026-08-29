/** Pure filtering, placement and grouping. */

import { describe, expect, it } from 'vitest';
import { ROUTE_STEP_NODES } from '../src/model/routes';
import type { Bill } from '../src/model/types';
import {
  DEFAULT_FILTERS,
  activeFilterCount,
  applyFilters,
  billTypeOptions,
  isDefaultFilters,
  matchesSearch,
  type FilterState,
} from '../src/selectors/filters';
import { billsAt, groupBills, placeBill, routeTotal } from '../src/selectors/grouping';
import { billById, exampleSnapshot } from './helpers';

const snapshot = exampleSnapshot();
const bills = snapshot.bills;

function withFilters(patch: Partial<FilterState>): FilterState {
  return { ...DEFAULT_FILTERS, ...patch };
}

describe('placement', () => {
  it('places every Bill exactly once', () => {
    const grouped = groupBills(bills);
    const routed = routeTotal(grouped, 'commons') + routeTotal(grouped, 'lords');
    expect(routed + grouped.special.length + grouped.concluded.length).toBe(bills.length);
  });

  it('never places the same Bill in two buckets', () => {
    const grouped = groupBills(bills);
    const seen = new Set<number>();
    const record = (bill: Bill): void => {
      expect(seen.has(bill.id)).toBe(false);
      seen.add(bill.id);
    };
    for (const routeId of ['commons', 'lords'] as const) {
      for (const bucket of grouped.routes[routeId].values()) bucket.forEach(record);
    }
    grouped.special.forEach(record);
    grouped.concluded.forEach(record);
    expect(seen.size).toBe(bills.length);
  });

  it('puts a Commons-origin Bill on the Commons route', () => {
    const bill = billById(9004); // Health Standards Bill, Commons report stage
    expect(placeBill(bill)).toEqual({
      kind: 'route',
      routeId: 'commons',
      node: 'commons_report',
    });
  });

  it('puts a Lords-origin Bill on the Lords route even when it is in the Commons', () => {
    const bill = billById(9016); // Charities Regulation Bill, Lords origin, Commons 2R
    expect(bill.originatingHouse).toBe('lords');
    expect(placeBill(bill)).toEqual({
      kind: 'route',
      routeId: 'lords',
      node: 'commons_second_reading',
    });
  });

  it('places an Act at Royal Assent rather than in a separate list', () => {
    const act = billById(9021);
    expect(act.status).toBe('enacted');
    expect(placeBill(act)).toEqual({ kind: 'route', routeId: 'commons', node: 'royal_assent' });
  });

  it('places withdrawn and defeated Bills in the concluded section', () => {
    expect(placeBill(billById(9023)).kind).toBe('concluded');
    expect(placeBill(billById(9024)).kind).toBe('concluded');
  });

  it('places a special-procedure Bill in the special section', () => {
    const bill = billById(9018);
    expect(bill.pipelineNode).toBe('special_procedure');
    expect(placeBill(bill).kind).toBe('special');
  });

  it('places an unrecognised stage in the special section rather than guessing', () => {
    const bill = billById(9019);
    expect(bill.pipelineNode).toBe('unknown');
    expect(placeBill(bill).kind).toBe('special');
  });

  it('never guesses a route for a Bill with no stated originating House', () => {
    const bill = billById(9020);
    expect(bill.originatingHouse).toBe('unassigned');
    expect(placeBill(bill).kind).toBe('special');
  });

  it('agrees with the count published in the snapshot', () => {
    const grouped = groupBills(bills);
    expect(grouped.special.length).toBe(snapshot.counts.specialOrUnclassified);
  });

  it('seeds every canonical stage so empty buckets stay visible', () => {
    const grouped = groupBills([]);
    for (const routeId of ['commons', 'lords'] as const) {
      expect([...grouped.routes[routeId].keys()]).toEqual([...ROUTE_STEP_NODES]);
      for (const node of ROUTE_STEP_NODES) {
        expect(billsAt(grouped, routeId, node)).toEqual([]);
      }
    }
  });
});

describe('status filtering', () => {
  it('defaults to Bills still in progress', () => {
    expect(DEFAULT_FILTERS.status).toBe('in_progress');
    const filtered = applyFilters(bills, DEFAULT_FILTERS);
    expect(filtered.length).toBeGreaterThan(0);
    for (const bill of filtered) {
      expect(['active', 'unknown']).toContain(bill.status);
    }
  });

  it('includes an unrecognised-stage Bill in the in-progress view', () => {
    const filtered = applyFilters(bills, DEFAULT_FILTERS);
    expect(filtered.map((bill) => bill.id)).toContain(9019);
  });

  it('shows only Acts when Acts are chosen', () => {
    const filtered = applyFilters(bills, withFilters({ status: 'acts' }));
    expect(filtered.length).toBe(snapshot.counts.enacted);
    for (const bill of filtered) expect(bill.status).toBe('enacted');
  });

  it('shows only withdrawn and defeated Bills when concluded is chosen', () => {
    const filtered = applyFilters(bills, withFilters({ status: 'concluded' }));
    expect(filtered.length).toBe(snapshot.counts.withdrawn + snapshot.counts.failed);
  });

  it('shows everything under all in session', () => {
    expect(applyFilters(bills, withFilters({ status: 'all' })).length).toBe(bills.length);
  });
});

describe('search', () => {
  it('matches the title, case-insensitively', () => {
    expect(matchesSearch(billById(9004), 'HEALTH')).toBe(true);
    expect(matchesSearch(billById(9004), 'health standards')).toBe(true);
  });

  it('matches a former title', () => {
    const bill = billById(9017);
    expect(bill.formerTitle).toBe('National Infrastructure Bill');
    expect(matchesSearch(bill, 'national infrastructure')).toBe(true);
  });

  it('matches the summary', () => {
    const bill = billById(9003);
    expect(bill.summary).not.toBeNull();
    expect(matchesSearch(bill, 'digital identity credentials')).toBe(true);
  });

  it('matches a sponsor name', () => {
    expect(matchesSearch(billById(9004), 'Wesley Marchant')).toBe(true);
  });

  it('does not match unrelated text', () => {
    expect(matchesSearch(billById(9004), 'zzzzz')).toBe(false);
  });

  it('treats blank and whitespace-only queries as no filter', () => {
    expect(matchesSearch(billById(9004), '')).toBe(true);
    expect(matchesSearch(billById(9004), '   ')).toBe(true);
  });
});

describe('combined filters', () => {
  it('narrows by originating House and stage together', () => {
    const filtered = applyFilters(
      bills,
      withFilters({ originatingHouse: 'lords', stage: 'lords_committee' }),
    );
    for (const bill of filtered) {
      expect(bill.originatingHouse).toBe('lords');
      expect(bill.pipelineNode).toBe('lords_committee');
    }
    expect(filtered.map((bill) => bill.id)).toEqual([9014]);
  });

  it('narrows by current House', () => {
    const filtered = applyFilters(bills, withFilters({ currentHouse: 'lords' }));
    for (const bill of filtered) expect(bill.currentHouse).toBe('lords');
  });

  it('narrows by Bill type', () => {
    const filtered = applyFilters(bills, withFilters({ billType: 'Government Bill' }));
    for (const bill of filtered) expect(bill.billType?.name).toBe('Government Bill');
  });

  it('can produce an empty result set', () => {
    const filtered = applyFilters(
      bills,
      withFilters({
        originatingHouse: 'commons',
        stage: 'lords_first_reading',
        search: 'zzzz',
      }),
    );
    expect(filtered).toEqual([]);
  });
});

describe('filter bookkeeping', () => {
  it('recognises the default state', () => {
    expect(isDefaultFilters(DEFAULT_FILTERS)).toBe(true);
    expect(isDefaultFilters(withFilters({ search: '  ' }))).toBe(true);
    expect(isDefaultFilters(withFilters({ status: 'all' }))).toBe(false);
  });

  it('counts the active filters', () => {
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0);
    expect(activeFilterCount(withFilters({ status: 'all', currentHouse: 'lords' }))).toBe(2);
    expect(activeFilterCount(withFilters({ search: 'health' }))).toBe(1);
  });

  it('offers the Bill types actually present, grouped by category', () => {
    const options = billTypeOptions(snapshot);
    expect(options.length).toBeGreaterThan(1);
    expect(options.map((option) => option.name)).toContain('Government Bill');
    const total = options.reduce((sum, option) => sum + option.count, 0);
    expect(total).toBeLessThanOrEqual(bills.length);
  });
});

describe('route ordering', () => {
  it('runs the Commons route through Commons stages, then Lords, then the shared steps', () => {
    expect(ROUTE_STEP_NODES.slice(0, 5)).toEqual([
      'commons_first_reading',
      'commons_second_reading',
      'commons_committee',
      'commons_report',
      'commons_third_reading',
    ]);
    expect(ROUTE_STEP_NODES.slice(10)).toEqual(['ping_pong', 'royal_assent']);
  });
});
