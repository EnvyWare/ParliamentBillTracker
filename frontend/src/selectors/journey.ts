/**
 * One Bill's actual path through the process.
 *
 * The snapshot records every stage occurrence a Bill has had, and what each
 * one mapped to. That is enough to mark the canonical route up with where the
 * Bill has been, where it is, and what it has not reached, without inventing
 * anything: a stage with no occurrence is reported as skipped rather than
 * quietly drawn as completed.
 */

import {
  branchPointsFor,
  orderedSteps,
  routeForOriginatingHouse,
  type BranchPoint,
  type Route,
} from '../model/routes';
import type { Bill, HistoryEntry, PipelineNode } from '../model/types';

export type StepState = 'completed' | 'current' | 'upcoming' | 'skipped' | 'stopped';

export interface JourneyStep {
  readonly node: PipelineNode;
  /** 1-based position in this Bill's route. */
  readonly step: number;
  readonly state: StepState;
  /** Occurrences of this stage in the Bill's own history. */
  readonly occurrences: readonly HistoryEntry[];
  /**
   * Procedural stages that ran while the Bill was at this point - carry-over
   * motions, programme motions and the like. They never move a Bill along the
   * route, so they hang off the node they happened at.
   */
  readonly sideEvents: readonly HistoryEntry[];
  readonly firstDate: string | null;
  readonly lastDate: string | null;
  /** The decision that follows this step, if there is one. */
  readonly branch: BranchPoint | null;
  /**
   * Which answer this Bill gave, where the data settles it. Null means the
   * Bill has not reached the decision, or the source does not say.
   */
  readonly branchAnswer: string | null;
}

export interface Journey {
  /** Null when the source data does not say which House the Bill started in. */
  readonly route: Route | null;
  readonly steps: readonly JourneyStep[];
  /** Side events that happened before any canonical stage. */
  readonly unplacedEvents: readonly HistoryEntry[];
  readonly currentStep: JourneyStep | null;
  readonly completedCount: number;
  readonly totalCount: number;
}

function datesOf(entries: readonly HistoryEntry[]): string[] {
  return entries
    .flatMap((entry) => entry.sittings.map((sitting) => sitting.date))
    .filter((date): date is string => date !== null)
    .sort();
}

export function buildJourney(bill: Bill): Journey {
  const route = routeForOriginatingHouse(bill.originatingHouse);
  const ordered = route === null ? [] : orderedSteps(route);
  const branches = route === null ? new Map<PipelineNode, BranchPoint>() : branchPointsFor(route);

  const occurrencesByNode = new Map<PipelineNode, HistoryEntry[]>();
  const sideEventsByNode = new Map<PipelineNode, HistoryEntry[]>();
  const unplacedEvents: HistoryEntry[] = [];

  // History is already in Parliament's own order, so walking it forwards
  // attributes each procedural stage to the canonical stage it followed.
  let lastCanonical: PipelineNode | null = null;
  for (const entry of bill.history) {
    if (entry.mappedNode !== null) {
      const bucket = occurrencesByNode.get(entry.mappedNode) ?? [];
      bucket.push(entry);
      occurrencesByNode.set(entry.mappedNode, bucket);
      lastCanonical = entry.mappedNode;
      continue;
    }
    if (lastCanonical === null) {
      unplacedEvents.push(entry);
      continue;
    }
    const bucket = sideEventsByNode.get(lastCanonical) ?? [];
    bucket.push(entry);
    sideEventsByNode.set(lastCanonical, bucket);
  }

  const terminal = bill.status === 'withdrawn' || bill.status === 'failed';
  const anchorNode = terminal ? bill.lastKnownPipelineNode : bill.pipelineNode;
  const anchorIndex = ordered.findIndex((step) => step.node === anchorNode);

  const steps: JourneyStep[] = ordered.map((step, index) => {
    const occurrences = occurrencesByNode.get(step.node) ?? [];
    const sideEvents = sideEventsByNode.get(step.node) ?? [];
    const dates = datesOf(occurrences);

    let state: StepState;
    if (anchorIndex === -1) {
      // The Bill is not on the canonical route at all; only what actually
      // happened is asserted.
      state = occurrences.length > 0 ? 'completed' : 'upcoming';
    } else if (index === anchorIndex) {
      if (terminal) state = 'stopped';
      else if (bill.status === 'enacted') state = 'completed';
      else state = 'current';
    } else if (index < anchorIndex) {
      state = occurrences.length > 0 ? 'completed' : 'skipped';
    } else {
      state = 'upcoming';
    }

    return {
      node: step.node,
      step: step.step,
      state,
      occurrences,
      sideEvents,
      firstDate: dates[0] ?? null,
      lastDate: dates.length > 0 ? (dates[dates.length - 1] ?? null) : null,
      branch: branches.get(step.node) ?? null,
      branchAnswer: null,
    };
  });

  return {
    route,
    steps: steps.map((step, index) => ({
      ...step,
      branchAnswer: answeredBranch(bill, steps, index, anchorIndex),
    })),
    unplacedEvents,
    currentStep: steps.find((step) => step.state === 'current' || step.state === 'stopped') ?? null,
    completedCount: steps.filter((step) => step.state === 'completed').length,
    totalCount: steps.length,
  };
}

export const STEP_STATE_LABEL: Record<StepState, string> = {
  completed: 'Completed',
  current: 'Current stage',
  upcoming: 'Not yet reached',
  skipped: 'Not recorded',
  stopped: 'Stopped here',
};

export const STEP_STATE_DESCRIPTION: Record<StepState, string> = {
  completed: 'This Bill has been through this stage.',
  current: 'This is where the Bill is now.',
  upcoming: 'The Bill has not reached this stage yet.',
  skipped:
    'The source data records no sitting for this stage, so it was either skipped or not published.',
  stopped: 'The Bill stopped here and is no longer progressing.',
};

/**
 * Which way a Bill actually went at a decision, where the record settles it.
 *
 * Only asserted when the evidence is unambiguous. A Bill that has simply not
 * reached a decision yet gets no answer, and neither does one where the
 * source data leaves the outcome open.
 */
function answeredBranch(
  bill: Bill,
  steps: readonly JourneyStep[],
  index: number,
  anchorIndex: number,
): string | null {
  const step = steps[index];
  if (step?.branch == null) return null;

  // A decision the Bill has not arrived at yet has no answer.
  if (anchorIndex !== -1 && index > anchorIndex) return null;

  const terminal = bill.status === 'withdrawn' || bill.status === 'failed';

  // Defeated at this very step: the Bill took the exit branch.
  if (bill.status === 'failed' && index === anchorIndex) return 'No';

  // Second House made no amendments, so the Bill skipped consideration.
  if (step.node === steps[9]?.node && !terminal) {
    const consideration = steps[10];
    const royalAssent = steps[11];
    if (consideration != null && royalAssent != null) {
      if (consideration.occurrences.length > 0) return 'Yes';
      if (royalAssent.occurrences.length > 0) return 'No';
    }
    return null;
  }

  // Consideration of amendments: agreed if it reached Royal Assent, still
  // exchanging if it is sitting in the loop.
  if (step.node === steps[10]?.node) {
    const royalAssent = steps[11];
    if (royalAssent != null && royalAssent.occurrences.length > 0) return 'Yes';
    if (index === anchorIndex) return 'No';
    return null;
  }

  // Any decision the Bill has moved past was answered in the affirmative.
  if (anchorIndex !== -1 && index < anchorIndex) return 'Yes';
  return null;
}
