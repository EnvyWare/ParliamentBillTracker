/**
 * Placing Bills onto the two routes, the special section, or the concluded list.
 *
 * The placement rule mirrors `is_special_or_unclassified` in the ingestion
 * code exactly, so the counts published in the snapshot and the sections
 * rendered here can never disagree.
 */

import { ROUTE_STEP_NODES } from '../model/routes';
import type { Bill, PipelineNode } from '../model/types';

const ROUTE_NODE_SET = new Set<PipelineNode>(ROUTE_STEP_NODES);
const UNPLACEABLE_NODES = new Set<PipelineNode>(['special_procedure', 'unknown']);

export type Placement =
  | { readonly kind: 'route'; readonly routeId: 'commons' | 'lords'; readonly node: PipelineNode }
  | { readonly kind: 'special' }
  | { readonly kind: 'concluded' };

/**
 * Decide where one Bill belongs. Every Bill gets exactly one placement.
 *
 * Withdrawn and defeated Bills form the concluded section. Enacted Bills are
 * placed at Royal Assent, which is the final step of both routes, rather than
 * being listed separately.
 */
export function placeBill(bill: Bill): Placement {
  if (bill.status === 'withdrawn' || bill.status === 'failed') {
    return { kind: 'concluded' };
  }
  if (UNPLACEABLE_NODES.has(bill.pipelineNode) || bill.originatingHouse === 'unassigned') {
    return { kind: 'special' };
  }
  // The originating House is known to be commons or lords by this point,
  // because an unassigned origin was already routed to the special section.
  if (ROUTE_NODE_SET.has(bill.pipelineNode)) {
    return { kind: 'route', routeId: bill.originatingHouse, node: bill.pipelineNode };
  }
  return { kind: 'special' };
}

export interface GroupedBills {
  /** routeId -> node -> Bills. Every route node is present, possibly empty. */
  readonly routes: Readonly<Record<'commons' | 'lords', ReadonlyMap<PipelineNode, Bill[]>>>;
  readonly special: readonly Bill[];
  readonly concluded: readonly Bill[];
  readonly total: number;
}

function emptyRouteMap(): Map<PipelineNode, Bill[]> {
  // Every canonical stage stays visible even with zero Bills in it, so the
  // buckets are seeded up front rather than created on demand.
  return new Map(ROUTE_STEP_NODES.map((node) => [node, [] as Bill[]]));
}

export function groupBills(bills: readonly Bill[]): GroupedBills {
  const routes = { commons: emptyRouteMap(), lords: emptyRouteMap() };
  const special: Bill[] = [];
  const concluded: Bill[] = [];

  for (const bill of bills) {
    const placement = placeBill(bill);
    switch (placement.kind) {
      case 'route':
        routes[placement.routeId].get(placement.node)?.push(bill);
        break;
      case 'special':
        special.push(bill);
        break;
      case 'concluded':
        concluded.push(bill);
        break;
    }
  }

  return { routes, special, concluded, total: bills.length };
}

export function billsAt(
  grouped: GroupedBills,
  routeId: 'commons' | 'lords',
  node: PipelineNode,
): readonly Bill[] {
  return grouped.routes[routeId].get(node) ?? [];
}

/** How many Bills a route panel currently shows. */
export function routeTotal(grouped: GroupedBills, routeId: 'commons' | 'lords'): number {
  let total = 0;
  for (const bucket of grouped.routes[routeId].values()) total += bucket.length;
  return total;
}
