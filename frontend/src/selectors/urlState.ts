/**
 * Filters and the selected Bill, expressed as query parameters.
 *
 * Copying the address bar has to reproduce the same view, so this is a pure,
 * reversible mapping with no hidden state.
 */

import { HOUSES, PIPELINE_NODES, type House, type PipelineNode } from '../model/types';
import { DEFAULT_FILTERS, STATUS_FILTERS, type FilterState, type StatusFilter } from './filters';

/** How a selected Bill is presented. */
export type BillView = 'summary' | 'journey';

export interface ViewState {
  readonly filters: FilterState;
  readonly selectedBillId: number | null;
  /**
   * 'summary' is the details sheet over the pipeline. 'journey' is the
   * dedicated page showing that one Bill's path through the whole process.
   */
  readonly billView: BillView;
}

export const DEFAULT_VIEW: ViewState = {
  filters: DEFAULT_FILTERS,
  selectedBillId: null,
  billView: 'summary',
};

const PARAM = {
  search: 'q',
  status: 'status',
  originatingHouse: 'origin',
  currentHouse: 'house',
  stage: 'stage',
  billType: 'type',
  bill: 'bill',
  billView: 'view',
} as const;

function readEnum<T extends string>(
  params: URLSearchParams,
  key: string,
  allowed: readonly T[],
): T | null {
  const value = params.get(key);
  if (value === null) return null;
  return (allowed as readonly string[]).includes(value) ? (value as T) : null;
}

export function parseViewState(search: string): ViewState {
  const params = new URLSearchParams(search);
  const billRaw = params.get(PARAM.bill);
  const billId = billRaw === null ? null : Number.parseInt(billRaw, 10);

  return {
    filters: {
      search: params.get(PARAM.search) ?? '',
      status:
        readEnum<StatusFilter>(params, PARAM.status, STATUS_FILTERS) ?? DEFAULT_FILTERS.status,
      originatingHouse: readEnum<House>(params, PARAM.originatingHouse, HOUSES),
      currentHouse: readEnum<House>(params, PARAM.currentHouse, HOUSES),
      stage: readEnum<PipelineNode>(params, PARAM.stage, PIPELINE_NODES),
      billType: params.get(PARAM.billType),
    },
    selectedBillId: billId !== null && Number.isFinite(billId) ? billId : null,
    billView: params.get(PARAM.billView) === 'journey' ? 'journey' : 'summary',
  };
}

/** Serialise to a query string. Defaults are omitted so shared links stay short. */
export function serialiseViewState(view: ViewState): string {
  const params = new URLSearchParams();
  const { filters } = view;

  if (filters.search.trim() !== '') params.set(PARAM.search, filters.search);
  if (filters.status !== DEFAULT_FILTERS.status) params.set(PARAM.status, filters.status);
  if (filters.originatingHouse !== null)
    params.set(PARAM.originatingHouse, filters.originatingHouse);
  if (filters.currentHouse !== null) params.set(PARAM.currentHouse, filters.currentHouse);
  if (filters.stage !== null) params.set(PARAM.stage, filters.stage);
  if (filters.billType !== null) params.set(PARAM.billType, filters.billType);
  if (view.selectedBillId !== null) {
    params.set(PARAM.bill, String(view.selectedBillId));
    if (view.billView === 'journey') params.set(PARAM.billView, 'journey');
  }

  const query = params.toString();
  return query === '' ? '' : `?${query}`;
}

/** The path plus query a given view should occupy. */
export function viewUrl(view: ViewState, pathname: string): string {
  const query = serialiseViewState(view);
  return query === '' ? pathname : `${pathname}${query}`;
}
