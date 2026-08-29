/**
 * Pure filtering. No React, no DOM, no dates from the ambient clock.
 *
 * Keeping this separate is what makes both the correctness and the speed of
 * filtering testable on their own.
 */

import type { Bill, House, PipelineNode, Snapshot } from '../model/types';

export const STATUS_FILTERS = ['in_progress', 'all', 'acts', 'concluded'] as const;
export type StatusFilter = (typeof STATUS_FILTERS)[number];

export const STATUS_FILTER_LABELS: Record<StatusFilter, string> = {
  in_progress: 'In progress',
  all: 'All in session',
  acts: 'Acts',
  concluded: 'Withdrawn or defeated',
};

export interface FilterState {
  readonly search: string;
  readonly status: StatusFilter;
  readonly originatingHouse: House | null;
  readonly currentHouse: House | null;
  readonly stage: PipelineNode | null;
  readonly billType: string | null;
}

export const DEFAULT_FILTERS: FilterState = {
  search: '',
  status: 'in_progress',
  originatingHouse: null,
  currentHouse: null,
  stage: null,
  billType: null,
};

export function isDefaultFilters(filters: FilterState): boolean {
  return (
    filters.search.trim() === '' &&
    filters.status === DEFAULT_FILTERS.status &&
    filters.originatingHouse === null &&
    filters.currentHouse === null &&
    filters.stage === null &&
    filters.billType === null
  );
}

export function activeFilterCount(filters: FilterState): number {
  let count = 0;
  if (filters.search.trim() !== '') count += 1;
  if (filters.status !== DEFAULT_FILTERS.status) count += 1;
  if (filters.originatingHouse !== null) count += 1;
  if (filters.currentHouse !== null) count += 1;
  if (filters.stage !== null) count += 1;
  if (filters.billType !== null) count += 1;
  return count;
}

function matchesStatus(bill: Bill, status: StatusFilter): boolean {
  switch (status) {
    case 'in_progress':
      // Unknown-stage Bills are still in progress; they are simply unplaced.
      return bill.status === 'active' || bill.status === 'unknown';
    case 'acts':
      return bill.status === 'enacted';
    case 'concluded':
      return bill.status === 'withdrawn' || bill.status === 'failed';
    case 'all':
      return true;
  }
}

/** Case-insensitive match across title, former title, summary and sponsors. */
export function matchesSearch(bill: Bill, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle === '') return true;

  if (bill.title.toLowerCase().includes(needle)) return true;
  if (bill.formerTitle !== null && bill.formerTitle.toLowerCase().includes(needle)) return true;
  if (bill.summary !== null && bill.summary.toLowerCase().includes(needle)) return true;
  return bill.sponsors.some((sponsor) => sponsor.name.toLowerCase().includes(needle));
}

export function matchesFilters(bill: Bill, filters: FilterState): boolean {
  if (!matchesStatus(bill, filters.status)) return false;
  if (filters.originatingHouse !== null && bill.originatingHouse !== filters.originatingHouse) {
    return false;
  }
  if (filters.currentHouse !== null && bill.currentHouse !== filters.currentHouse) return false;
  if (filters.stage !== null && bill.pipelineNode !== filters.stage) return false;
  if (filters.billType !== null && (bill.billType?.name ?? null) !== filters.billType) return false;
  return matchesSearch(bill, filters.search);
}

export function applyFilters(bills: readonly Bill[], filters: FilterState): Bill[] {
  return bills.filter((bill) => matchesFilters(bill, filters));
}

export interface BillTypeOption {
  readonly name: string;
  readonly category: string | null;
  readonly count: number;
}

/** Bill types present in the snapshot, for the filter control. */
export function billTypeOptions(snapshot: Snapshot): BillTypeOption[] {
  const seen = new Map<string, BillTypeOption>();
  for (const bill of snapshot.bills) {
    const name = bill.billType?.name;
    if (name === undefined) continue;
    const existing = seen.get(name);
    seen.set(name, {
      name,
      category: bill.billType?.category ?? null,
      count: (existing?.count ?? 0) + 1,
    });
  }
  return [...seen.values()].sort(
    (a, b) => (a.category ?? '').localeCompare(b.category ?? '') || a.name.localeCompare(b.name),
  );
}

/** Stages present in the snapshot, for the current-stage filter control. */
export function stageOptions(snapshot: Snapshot): PipelineNode[] {
  const seen = new Set<PipelineNode>();
  for (const bill of snapshot.bills) seen.add(bill.pipelineNode);
  return [...seen];
}
