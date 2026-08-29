import { useId } from 'react';
import {
  EDGE_SOURCE,
  VIEW_HEIGHT,
  VIEW_WIDTH,
  buildFlowLayout,
  type FlowEdge,
  type FlowNode,
} from '../model/flowLayout';
import type { Bill, PipelineNode } from '../model/types';
import { STEP_STATE_LABEL, type Journey, type StepState } from '../selectors/journey';

type EdgeState = 'taken' | 'available' | 'untaken';

interface BillFlowDiagramProps {
  readonly bill: Bill;
  readonly journey: Journey;
}

/** Was this stage reached at all? */
function reached(state: StepState | undefined): boolean {
  return state === 'completed' || state === 'current' || state === 'stopped';
}

/**
 * One Bill's route, drawn as a flow diagram.
 *
 * The picture is decorative in the accessibility sense - it is marked as an
 * image with a summary - and the same information is published beside it as
 * real text, so nothing is available only to people who can see the diagram.
 */
export function BillFlowDiagram({ bill, journey }: BillFlowDiagramProps): React.JSX.Element {
  const ids = useId();
  const titleId = `${ids}-title`;
  const descId = `${ids}-desc`;

  const orderedNodes = journey.steps.map((step) => step.node);
  const layout = buildFlowLayout(bill.originatingHouse, orderedNodes);
  const stateByNode = new Map<PipelineNode, StepState>(
    journey.steps.map((step) => [step.node, step.state]),
  );

  const terminal = bill.status === 'withdrawn' || bill.status === 'failed';
  const pingPong = journey.steps.find((step) => step.node === orderedNodes[10]);
  const royalAssent = journey.steps.find((step) => step.node === orderedNodes[11]);
  const exchanges = pingPong?.occurrences.length ?? 0;

  function nodeState(node: FlowNode): StepState | 'start' | 'end' | 'fail' | 'decision' {
    if (node.kind === 'terminal-start') return 'start';
    if (node.kind === 'terminal-end') return bill.status === 'enacted' ? 'end' : 'upcoming';
    if (node.kind === 'terminal-fail') return terminal ? 'fail' : 'upcoming';
    if (node.kind === 'process') {
      return reached(stateByNode.get(orderedNodes[5] ?? 'unknown')) ? 'completed' : 'upcoming';
    }
    if (node.kind === 'decision') {
      if (exchanges > 0 || royalAssent?.state === 'completed') return 'completed';
      return 'upcoming';
    }
    return node.node === undefined ? 'upcoming' : (stateByNode.get(node.node) ?? 'upcoming');
  }

  function edgeState(edge: FlowEdge): EdgeState {
    const fallback: EdgeState = terminal ? 'untaken' : 'available';

    if (edge.kind === 'reject') {
      if (bill.status !== 'failed') return 'untaken';
      const source = EDGE_SOURCE[edge.id];
      if (edge.id === 'pingpong-falls') {
        return pingPong?.state === 'stopped' ? 'taken' : 'untaken';
      }
      const sourceNode = source === undefined ? undefined : nodeIdToPipeline(source);
      return sourceNode !== undefined && stateByNode.get(sourceNode) === 'stopped'
        ? 'taken'
        : 'untaken';
    }

    switch (edge.id) {
      case 'decision-royal-assent':
        return royalAssent?.state === 'completed' ? 'taken' : fallback;
      case 'decision-pingpong':
        return exchanges > 0 ? 'taken' : fallback;
      case 'pingpong-decision':
        // Drawn as travelled only when the Houses actually exchanged twice.
        return exchanges > 1 ? 'taken' : fallback;
      case 'royal-assent-act':
        return bill.status === 'enacted' ? 'taken' : fallback;
      default:
        break;
    }

    const source = EDGE_SOURCE[edge.id];
    if (source === undefined) return fallback;
    if (source === 'start')
      return reached(stateByNode.get(orderedNodes[0] ?? 'unknown')) ? 'taken' : fallback;
    if (source === 'transfer')
      return reached(stateByNode.get(orderedNodes[5] ?? 'unknown')) ? 'taken' : fallback;

    const sourceNode = nodeIdToPipeline(source);
    if (sourceNode === undefined) return fallback;
    // A spine edge counts as travelled once the Bill has moved past its source.
    return stateByNode.get(sourceNode) === 'completed' ? 'taken' : fallback;
  }

  function nodeIdToPipeline(nodeId: string): PipelineNode | undefined {
    const match = /^(fh|sh)-(\d)$/.exec(nodeId);
    if (match === null) return undefined;
    const offset = match[1] === 'fh' ? 0 : 5;
    return orderedNodes[offset + Number(match[2])];
  }

  const summary =
    `Flow diagram of the ${layout.lanes[0]?.label ?? ''} route for ${bill.title}. ` +
    `${journey.completedCount} of ${journey.totalCount} stages completed. ` +
    (journey.currentStep === null ? '' : `Currently at step ${journey.currentStep.step}. `);

  return (
    // The diagram is wider than a phone, so it scrolls in its own box. A
    // scrollable region has to be reachable by keyboard, hence the tabIndex.
    <div
      className="flow-scroll"
      tabIndex={0}
      role="group"
      aria-label={`Flow diagram for ${bill.title}`}
    >
      <svg
        className="flow"
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        role="img"
        aria-labelledby={titleId}
        aria-describedby={descId}
      >
        <title id={titleId}>How {bill.title} moves through Parliament</title>
        <desc id={descId}>
          {summary}
          The full route is also listed as text below the diagram.
        </desc>

        <defs>
          {(['taken', 'available', 'untaken'] as const).map((state) => (
            <marker
              key={state}
              id={`${ids}-arrow-${state}`}
              viewBox="0 0 10 10"
              refX="10"
              refY="5"
              markerWidth="9"
              markerHeight="9"
              /* User-space units, so a thicker "taken" edge does not also get
                 a bigger arrowhead that overshoots into the node. refX at the
                 tip puts the point exactly on the node edge. */
              markerUnits="userSpaceOnUse"
              orient="auto"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" className={`flow__head flow__head--${state}`} />
            </marker>
          ))}
        </defs>

        {/* Swimlanes. Decorative grouping; the House is named in the label. */}
        {layout.lanes.map((lane) => (
          <g key={lane.id}>
            <rect
              className={`flow__lane flow__lane--${lane.house}`}
              x={lane.x}
              y={lane.y}
              width={lane.width}
              height={lane.height}
              rx="14"
            />
            <text className="flow__lane-label" x={lane.x + 14} y={lane.y + 20}>
              {lane.label}
            </text>
          </g>
        ))}

        {layout.edges.map((edge) => {
          const state = edgeState(edge);
          return (
            <g key={edge.id}>
              <path
                className={`flow__edge flow__edge--${edge.kind} flow__edge--${state}`}
                d={edge.d}
                markerEnd={`url(#${ids}-arrow-${state})`}
              />
              {edge.label !== undefined &&
                edge.labelX !== undefined &&
                edge.labelY !== undefined && (
                  <text
                    className={`flow__edge-label flow__edge-label--${state}`}
                    x={edge.labelX}
                    y={edge.labelY}
                    textAnchor={edge.kind === 'reject' || edge.kind === 'loop' ? 'middle' : 'start'}
                  >
                    {edge.label}
                  </text>
                )}
            </g>
          );
        })}

        {layout.nodes.map((node) => {
          const state = nodeState(node);
          const x = node.cx - node.width / 2;
          const y = node.cy - node.height / 2;
          const isDecision = node.kind === 'decision';
          const firstLineY = node.cy - ((node.lines.length - 1) * 15) / 2 + 5;

          return (
            <g className={`flow__node flow__node--${state}`} key={node.id}>
              {isDecision ? (
                <polygon
                  className="flow__shape flow__shape--decision"
                  points={`${node.cx},${y} ${node.cx + node.width / 2},${node.cy} ${node.cx},${y + node.height} ${node.cx - node.width / 2},${node.cy}`}
                />
              ) : (
                <rect
                  className={`flow__shape flow__shape--${node.kind}`}
                  x={x}
                  y={y}
                  width={node.width}
                  height={node.height}
                  rx={node.kind.startsWith('terminal') ? node.height / 2 : 8}
                />
              )}

              {node.step !== undefined && (
                <>
                  <circle className="flow__step" cx={x + 18} cy={node.cy} r="11" />
                  <text className="flow__step-text" x={x + 18} y={node.cy + 4}>
                    {node.step}
                  </text>
                </>
              )}

              <text
                className="flow__label"
                x={node.step === undefined ? node.cx : node.cx + 10}
                y={firstLineY}
              >
                {node.lines.map((line, index) => (
                  <tspan
                    key={line}
                    x={node.step === undefined ? node.cx : node.cx + 10}
                    dy={index === 0 ? 0 : 15}
                  >
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
      </svg>

      {/* The same route as text, so the diagram is never the only source. */}
      <ol className="visually-hidden">
        {journey.steps.map((step) => (
          <li key={step.node}>
            Step {step.step}: {step.node.replace(/_/g, ' ')} — {STEP_STATE_LABEL[step.state]}.
          </li>
        ))}
      </ol>
    </div>
  );
}
