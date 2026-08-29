/**
 * Geometry for the Bill flow diagram.
 *
 * The graph shape is the same for every Bill - only the states change - so the
 * layout is authored once here rather than computed at runtime. That keeps the
 * diagram deterministic, keeps it out of the bundle budget (no layout
 * library), and means the long "Rejected" edges can be routed deliberately
 * instead of by an algorithm that does not know what they mean.
 *
 * `docs/process-model.md` holds the Mermaid source this is drawn from.
 *
 * Coordinates are in the SVG user space of VIEW_BOX. The diagram scales with
 * its container; on a narrow screen it scrolls inside its own box rather than
 * shrinking the text to nothing.
 */

import type { House, PipelineNode } from './types';

export const VIEW_WIDTH = 720;
export const VIEW_HEIGHT = 1210;

export type FlowNodeKind =
  'terminal-start' | 'terminal-end' | 'terminal-fail' | 'stage' | 'process' | 'decision';

export interface FlowNode {
  readonly id: string;
  readonly kind: FlowNodeKind;
  /** Centre point. */
  readonly cx: number;
  readonly cy: number;
  readonly width: number;
  readonly height: number;
  /** Pre-split, because SVG text does not wrap. */
  readonly lines: readonly string[];
  /** Present for the twelve numbered stages. */
  readonly node?: PipelineNode;
  readonly step?: number;
}

export type FlowEdgeKind = 'spine' | 'reject' | 'branch' | 'loop';

export interface FlowEdge {
  readonly id: string;
  readonly kind: FlowEdgeKind;
  /** SVG path data. */
  readonly d: string;
  readonly label?: string;
  readonly labelX?: number;
  readonly labelY?: number;
}

export interface FlowLane {
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
  /**
   * The whole label, for the text alternative and for tests.
   *
   * It is deliberately not what gets drawn. The spine runs down the middle of
   * the lane, so a single label anchored at the lane's left edge collides with
   * it as soon as the House name is long or the body font is wide. The two
   * halves below are drawn either side of the spine instead, which cannot
   * collide with it whatever the font does.
   */
  readonly label: string;
  /** Drawn at the lane's top left, ending well before the spine. */
  readonly houseName: string;
  /** Drawn at the lane's top right, starting well after the spine. */
  readonly position: string;
  readonly house: House;
}

export interface FlowLayout {
  readonly lanes: readonly FlowLane[];
  readonly nodes: readonly FlowNode[];
  readonly edges: readonly FlowEdge[];
}

const SPINE = 400;
const STAGE_W = 190;
const STAGE_H = 44;
const STAGE_LEFT = SPINE - STAGE_W / 2;

/** Vertical centres of the five stages in each lane. */
const FIRST_HOUSE_Y = [150, 216, 282, 348, 414] as const;
const SECOND_HOUSE_Y = [594, 660, 726, 792, 858] as const;

/**
 * Vertical channels the long "Rejected" edges run down, left of the spine.
 * All four sit left of the ping-pong box (which starts at x=120) so no edge
 * ever crosses a node on its way to "Bill falls".
 */
const REJECT_CHANNELS = [105, 80, 55, 30] as const;

const FALLS_TOP = 1137;

const HOUSE_NAME: Record<House, string> = {
  commons: 'House of Commons',
  lords: 'House of Lords',
  unassigned: 'the other House',
};

function stage(id: string, node: PipelineNode, step: number, cy: number, label: string): FlowNode {
  return {
    id,
    kind: 'stage',
    cx: SPINE,
    cy,
    width: STAGE_W,
    height: STAGE_H,
    lines: [label],
    node,
    step,
  };
}

/**
 * A straight vertical spine edge between two stacked nodes.
 *
 * `labelY` can be overridden where the midpoint would put the text on a
 * swimlane border.
 */
function spine(id: string, fromY: number, toY: number, label?: string, labelY?: number): FlowEdge {
  return {
    id,
    kind: 'spine',
    d: `M ${SPINE},${fromY} V ${toY}`,
    ...(label === undefined
      ? {}
      : { label, labelX: SPINE + 12, labelY: labelY ?? (fromY + toY) / 2 + 4 }),
  };
}

/**
 * A rejection: out of the left of a stage, down its own channel, into the top
 * of "Bill falls". Routed by hand so the four of them never cross.
 */
function reject(id: string, fromY: number, channel: number, labelY: number): FlowEdge {
  return {
    id,
    kind: 'reject',
    d: `M ${STAGE_LEFT},${fromY} H ${channel + 30} Q ${channel},${fromY} ${channel},${fromY + 30} V ${FALLS_TOP}`,
    label: 'Rejected',
    labelX: channel,
    labelY,
  };
}

/**
 * Build the diagram for one Bill's route.
 *
 * The House names are the Bill's own, so a Lords-first Bill reads "First
 * House: House of Lords" rather than a generic label.
 */
export function buildFlowLayout(
  firstHouse: House,
  orderedNodes: readonly PipelineNode[],
): FlowLayout {
  const secondHouse: House = firstHouse === 'commons' ? 'lords' : 'commons';
  const firstName = HOUSE_NAME[firstHouse];
  const secondName = HOUSE_NAME[secondHouse];

  const stageLabels: readonly string[] = [
    'First Reading',
    'Second Reading',
    'Committee Stage',
    'Report Stage',
    'Third Reading',
  ];
  const labelAt = (index: number): string => stageLabels[index] ?? 'Stage';

  const nodes: FlowNode[] = [
    {
      id: 'start',
      kind: 'terminal-start',
      cx: SPINE,
      cy: 42,
      width: 280,
      height: 52,
      lines: ['Bill introduced in the', firstName],
    },
    ...FIRST_HOUSE_Y.map((cy, index) =>
      stage(`fh-${index}`, orderedNodes[index] ?? 'unknown', index + 1, cy, labelAt(index)),
    ),
    {
      id: 'transfer',
      kind: 'process',
      cx: SPINE,
      cy: 490,
      width: 250,
      height: 46,
      lines: [`Sent to the ${secondName}`],
    },
    ...SECOND_HOUSE_Y.map((cy, index) =>
      stage(`sh-${index}`, orderedNodes[index + 5] ?? 'unknown', index + 6, cy, labelAt(index)),
    ),
    {
      id: 'decision',
      kind: 'decision',
      cx: SPINE,
      cy: 950,
      width: 230,
      height: 100,
      lines: ['Both Houses agree', 'the exact text?'],
    },
    {
      id: 'pingpong',
      kind: 'stage',
      cx: 235,
      cy: 1075,
      width: 230,
      height: 52,
      lines: ['Consideration of', 'amendments (ping-pong)'],
      node: orderedNodes[10] ?? 'ping_pong',
      step: 11,
    },
    {
      id: 'royal-assent',
      kind: 'stage',
      cx: 590,
      cy: 1055,
      width: 150,
      height: 44,
      lines: ['Royal Assent'],
      node: orderedNodes[11] ?? 'royal_assent',
      step: 12,
    },
    {
      id: 'act',
      kind: 'terminal-end',
      cx: 590,
      cy: 1140,
      width: 170,
      height: 46,
      lines: ['Act of Parliament'],
    },
    {
      id: 'falls',
      kind: 'terminal-fail',
      cx: 95,
      cy: 1163,
      width: 150,
      height: 46,
      lines: ['Bill falls'],
    },
  ];

  const edges: FlowEdge[] = [
    spine('start-fh0', 68, 128),
    spine('fh0-fh1', 172, 194),
    spine('fh1-fh2', 238, 260, 'Passed'),
    spine('fh2-fh3', 304, 326),
    spine('fh3-fh4', 370, 392),
    spine('fh4-transfer', 436, 467, 'Passed'),
    spine('transfer-sh0', 513, 572),
    spine('sh0-sh1', 616, 638),
    spine('sh1-sh2', 682, 704, 'Passed'),
    spine('sh2-sh3', 748, 770),
    spine('sh3-sh4', 814, 836),
    spine('sh4-decision', 880, 900, 'Passed', 899),

    reject('reject-fh1', 216, REJECT_CHANNELS[0], 300),
    reject('reject-fh4', 414, REJECT_CHANNELS[1], 500),
    reject('reject-sh1', 660, REJECT_CHANNELS[2], 760),
    reject('reject-sh4', 858, REJECT_CHANNELS[3], 960),

    {
      id: 'decision-royal-assent',
      kind: 'branch',
      d: 'M 515,950 H 560 Q 590,950 590,980 V 1033',
      label: 'Yes',
      labelX: 601,
      labelY: 1000,
    },
    {
      id: 'decision-pingpong',
      kind: 'branch',
      d: 'M 400,1000 V 1018 Q 400,1032 380,1032 H 255 Q 235,1032 235,1049',
      label: 'Further changes',
      labelX: 318,
      labelY: 1026,
    },
    {
      // The exchange repeats until the two Houses agree, so this goes back.
      id: 'pingpong-decision',
      kind: 'loop',
      d: 'M 175,1049 V 986 Q 175,950 285,950',
      label: 'Sent back',
      labelX: 175,
      labelY: 978,
    },
    {
      id: 'pingpong-falls',
      kind: 'reject',
      d: 'M 165,1101 V 1120 Q 165,1132 150,1132 H 145 Q 135,1132 135,1137',
      label: 'Session ends',
      labelX: 250,
      labelY: 1126,
    },
    {
      id: 'royal-assent-act',
      kind: 'spine',
      d: 'M 590,1077 V 1117',
    },
  ];

  const lanes: FlowLane[] = [
    {
      id: 'lane-first',
      x: 250,
      y: 96,
      width: 300,
      height: 348,
      label: `First House · ${firstName}`,
      houseName: firstName,
      position: 'First House',
      house: firstHouse,
    },
    {
      id: 'lane-second',
      x: 250,
      y: 540,
      width: 300,
      height: 348,
      label: `Second House · ${secondName}`,
      houseName: secondName,
      position: 'Second House',
      house: secondHouse,
    },
  ];

  return { lanes, nodes, edges };
}

/** Which stage node an edge leaves, for deciding whether it was travelled. */
export const EDGE_SOURCE: Record<string, string> = {
  'start-fh0': 'start',
  'fh0-fh1': 'fh-0',
  'fh1-fh2': 'fh-1',
  'fh2-fh3': 'fh-2',
  'fh3-fh4': 'fh-3',
  'fh4-transfer': 'fh-4',
  'transfer-sh0': 'transfer',
  'sh0-sh1': 'sh-0',
  'sh1-sh2': 'sh-1',
  'sh2-sh3': 'sh-2',
  'sh3-sh4': 'sh-3',
  'sh4-decision': 'sh-4',
  'reject-fh1': 'fh-1',
  'reject-fh4': 'fh-4',
  'reject-sh1': 'sh-1',
  'reject-sh4': 'sh-4',
};
