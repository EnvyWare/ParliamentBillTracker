/**
 * The two canonical routes a Bill can take, and what each step means.
 *
 * Both routes are always rendered. Seeing that a Bill can start in either
 * House, and that the two routes are mirror images which converge on the same
 * final two steps, is part of the explanation rather than a detail to hide
 * behind a tab.
 *
 * All wording here is original. It describes the process as set out in
 * Parliament's own public guidance on the passage of a Bill.
 */

import type { House, PipelineNode } from './types';

export interface NodeInfo {
  /** Name shown as the bucket heading. */
  readonly label: string;
  /** One short sentence, always visible: never hover-only. */
  readonly explanation: string;
  readonly house: House | 'both';
}

export const NODE_INFO: Record<PipelineNode, NodeInfo> = {
  commons_first_reading: {
    label: 'Commons: First Reading',
    explanation: 'The Bill is formally introduced to the Commons. There is no debate and no vote.',
    house: 'commons',
  },
  commons_second_reading: {
    label: 'Commons: Second Reading',
    explanation: 'MPs hold the first full debate on the general principles of the Bill.',
    house: 'commons',
  },
  commons_committee: {
    label: 'Commons: Committee Stage',
    explanation: 'A committee of MPs examines the Bill line by line and can amend it.',
    house: 'commons',
  },
  commons_report: {
    label: 'Commons: Report Stage',
    explanation: 'The whole House reviews the amended Bill and can make further changes.',
    house: 'commons',
  },
  commons_third_reading: {
    label: 'Commons: Third Reading',
    explanation:
      'MPs debate and vote on the final version of the Bill as it stands in the Commons.',
    house: 'commons',
  },
  lords_first_reading: {
    label: 'Lords: First Reading',
    explanation: 'The Bill is formally introduced to the Lords. There is no debate and no vote.',
    house: 'lords',
  },
  lords_second_reading: {
    label: 'Lords: Second Reading',
    explanation: 'Members of the Lords hold the first full debate on the principles of the Bill.',
    house: 'lords',
  },
  lords_committee: {
    label: 'Lords: Committee Stage',
    explanation: 'The Lords examine the Bill line by line. Every clause can be debated.',
    house: 'lords',
  },
  lords_report: {
    label: 'Lords: Report Stage',
    explanation: 'The Lords review the amended Bill and can make further changes.',
    house: 'lords',
  },
  lords_third_reading: {
    label: 'Lords: Third Reading',
    explanation: 'A final chance for the Lords to tidy up the wording before the Bill moves on.',
    house: 'lords',
  },
  ping_pong: {
    label: 'Consideration of Amendments',
    explanation: 'Ping-pong: both Houses agree the final wording.',
    house: 'both',
  },
  royal_assent: {
    label: 'Royal Assent',
    explanation: 'The Bill is agreed by the monarch and becomes an Act of Parliament.',
    house: 'both',
  },
  special_procedure: {
    label: 'Other or special Parliamentary procedure',
    explanation:
      'These Bills are following a procedure that does not map onto the standard route, such as a Private Bill examination.',
    house: 'both',
  },
  withdrawn: {
    label: 'Withdrawn',
    explanation: 'The Bill was withdrawn and is no longer progressing.',
    house: 'both',
  },
  failed: {
    label: 'Defeated',
    explanation: 'The Bill was defeated in a vote and is no longer progressing.',
    house: 'both',
  },
  unknown: {
    label: 'Not yet classified',
    explanation:
      'These Bills are at a stage this site does not yet recognise. They are shown here rather than being placed by guesswork.',
    house: 'both',
  },
};

export interface RouteStep {
  readonly node: PipelineNode;
  /** 1-based position in the legislative sequence for this route. */
  readonly step: number;
}

export interface RoutePhase {
  readonly id: string;
  /** Heading for the group of stages, e.g. "First House: House of Commons". */
  readonly title: string;
  readonly house: House | 'both';
  readonly steps: readonly RouteStep[];
}

export interface Route {
  readonly id: 'commons' | 'lords';
  /** Panel heading. */
  readonly title: string;
  readonly summary: string;
  /** Explanatory marker between the two Houses. Not a data bucket. */
  readonly transferLabel: string;
  readonly phases: readonly RoutePhase[];
}

const COMMONS_STAGES: readonly PipelineNode[] = [
  'commons_first_reading',
  'commons_second_reading',
  'commons_committee',
  'commons_report',
  'commons_third_reading',
];

const LORDS_STAGES: readonly PipelineNode[] = [
  'lords_first_reading',
  'lords_second_reading',
  'lords_committee',
  'lords_report',
  'lords_third_reading',
];

const SHARED_STAGES: readonly PipelineNode[] = ['ping_pong', 'royal_assent'];

function buildRoute(
  id: 'commons' | 'lords',
  title: string,
  summary: string,
  transferLabel: string,
  first: readonly PipelineNode[],
  second: readonly PipelineNode[],
  firstTitle: string,
  secondTitle: string,
  firstHouse: House,
  secondHouse: House,
): Route {
  let step = 0;
  const toSteps = (nodes: readonly PipelineNode[]): RouteStep[] =>
    nodes.map((node) => ({ node, step: ++step }));

  return {
    id,
    title,
    summary,
    transferLabel,
    phases: [
      { id: `${id}-first`, title: firstTitle, house: firstHouse, steps: toSteps(first) },
      { id: `${id}-second`, title: secondTitle, house: secondHouse, steps: toSteps(second) },
      {
        id: `${id}-shared`,
        title: 'Both Houses, then law',
        house: 'both',
        steps: toSteps(SHARED_STAGES),
      },
    ],
  };
}

export const COMMONS_ROUTE: Route = buildRoute(
  'commons',
  'Starts in the House of Commons',
  'Most Government Bills take this route. The Commons considers the Bill first, then the Lords.',
  'Passes to the House of Lords',
  COMMONS_STAGES,
  LORDS_STAGES,
  'First House: House of Commons',
  'Second House: House of Lords',
  'commons',
  'lords',
);

export const LORDS_ROUTE: Route = buildRoute(
  'lords',
  'Starts in the House of Lords',
  'A Bill can equally begin in the Lords. The same stages happen, in the opposite order.',
  'Passes to the House of Commons',
  LORDS_STAGES,
  COMMONS_STAGES,
  'First House: House of Lords',
  'Second House: House of Commons',
  'lords',
  'commons',
);

export const ROUTES: readonly Route[] = [COMMONS_ROUTE, LORDS_ROUTE];

/** Every node that appears as a step on a route, in either route's ordering. */
export const ROUTE_STEP_NODES: readonly PipelineNode[] = [
  ...COMMONS_STAGES,
  ...LORDS_STAGES,
  ...SHARED_STAGES,
];

export function routeForOriginatingHouse(house: House): Route | null {
  if (house === 'commons') return COMMONS_ROUTE;
  if (house === 'lords') return LORDS_ROUTE;
  // An unassigned origin is never guessed onto a route.
  return null;
}

/**
 * Decision points and branches.
 *
 * The twelve canonical steps are the spine of the process, but a Bill does
 * not simply walk down them. It is voted on, it can fall, the second House
 * may not amend it at all, and consideration of amendments is a loop rather
 * than a single step. These branch points describe that honestly without
 * turning any of them into a bucket that holds Bills: a Bill is always at
 * exactly one of the twelve steps.
 *
 * Positions are given by index into a route's ordered steps, so the same
 * definitions produce the right stage names for both origin routes.
 */

export type BranchKind = 'continue' | 'exit' | 'skip' | 'loop';

export interface BranchOutcome {
  readonly kind: BranchKind;
  /** Short answer to the question, e.g. "No". */
  readonly answer: string;
  readonly consequence: string;
}

export interface BranchPoint {
  /** The step this decision follows. */
  readonly afterNode: PipelineNode;
  readonly question: string;
  readonly outcomes: readonly BranchOutcome[];
}

const FIRST_HOUSE_SECOND_READING = 1;
const FIRST_HOUSE_THIRD_READING = 4;
const SECOND_HOUSE_SECOND_READING = 6;
const SECOND_HOUSE_THIRD_READING = 9;
const CONSIDERATION = 10;

/** Every step of a route, in order, flattened out of its phases. */
export function orderedSteps(route: Route): RouteStep[] {
  return route.phases.flatMap((phase) => phase.steps);
}

export function branchPointsFor(route: Route): Map<PipelineNode, BranchPoint> {
  const steps = orderedSteps(route);
  const nodeAt = (index: number): PipelineNode => steps[index]?.node ?? 'unknown';

  const firstHouse = route.id === 'commons' ? 'the Commons' : 'the Lords';
  const secondHouse = route.id === 'commons' ? 'the Lords' : 'the Commons';

  const points: BranchPoint[] = [
    {
      afterNode: nodeAt(FIRST_HOUSE_SECOND_READING),
      question: `Does ${firstHouse} vote for the Bill's principle?`,
      outcomes: [
        { kind: 'continue', answer: 'Yes', consequence: 'The Bill goes to committee.' },
        {
          kind: 'exit',
          answer: 'No',
          consequence: 'The Bill is defeated and goes no further.',
        },
      ],
    },
    {
      afterNode: nodeAt(FIRST_HOUSE_THIRD_READING),
      question: `Does ${firstHouse} pass the Bill?`,
      outcomes: [
        { kind: 'continue', answer: 'Yes', consequence: `The Bill passes to ${secondHouse}.` },
        { kind: 'exit', answer: 'No', consequence: 'The Bill is defeated and goes no further.' },
      ],
    },
    {
      afterNode: nodeAt(SECOND_HOUSE_SECOND_READING),
      question: `Does ${secondHouse} vote for the Bill's principle?`,
      outcomes: [
        { kind: 'continue', answer: 'Yes', consequence: 'The Bill goes to committee.' },
        { kind: 'exit', answer: 'No', consequence: 'The Bill is defeated and goes no further.' },
      ],
    },
    {
      afterNode: nodeAt(SECOND_HOUSE_THIRD_READING),
      question: `Did ${secondHouse} change the Bill?`,
      outcomes: [
        {
          kind: 'skip',
          answer: 'No',
          consequence: 'Both Houses already agree, so the Bill goes straight to Royal Assent.',
        },
        {
          kind: 'continue',
          answer: 'Yes',
          consequence: 'The amendments go back for consideration.',
        },
      ],
    },
    {
      afterNode: nodeAt(CONSIDERATION),
      question: 'Do both Houses now agree the same text?',
      outcomes: [
        { kind: 'continue', answer: 'Yes', consequence: 'The Bill goes for Royal Assent.' },
        {
          kind: 'loop',
          answer: 'No',
          consequence: 'It goes back to the other House for another exchange.',
        },
      ],
    },
  ];

  return new Map(points.map((point) => [point.afterNode, point]));
}

/** Outcomes that can end a Bill at any point, rather than at one step. */
export const ANYTIME_OUTCOMES: readonly { title: string; detail: string }[] = [
  {
    title: 'Withdrawn',
    detail: 'The member or government in charge of a Bill can withdraw it at any point.',
  },
  {
    title: 'Runs out of time',
    detail:
      'A Bill that has not completed its stages when the session ends falls, unless it is carried over into the next session.',
  },
];
