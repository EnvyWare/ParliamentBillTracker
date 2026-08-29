import { useEffect, useState } from 'react';
import { NARROW_QUERY, useMediaQuery } from '../hooks/useMediaQuery';
import { branchPointsFor, type Route, type RoutePhase } from '../model/routes';
import type { Bill, PipelineNode } from '../model/types';
import { billsAt, routeTotal, type GroupedBills } from '../selectors/grouping';
import { StageBucket } from './StageBucket';

interface HousePhaseProps {
  readonly route: Route;
  readonly phase: RoutePhase;
  readonly bills: (node: PipelineNode) => readonly Bill[];
  readonly onSelect: (billId: number) => void;
}

/**
 * One House's block of stages, or the shared final steps.
 *
 * The DOM order is the legislative order, so tabbing through the page walks
 * the process in the order it actually happens.
 */
export function HousePhase({ route, phase, bills, onSelect }: HousePhaseProps): React.JSX.Element {
  const headingId = `${phase.id}-heading`;
  const branches = branchPointsFor(route);
  return (
    <section className={`phase phase--${phase.house}`} aria-labelledby={headingId}>
      <h3 className="phase__title" id={headingId}>
        {phase.title}
      </h3>
      <ol className="phase__stages">
        {phase.steps.map((step) => (
          <li key={step.node}>
            <StageBucket
              node={step.node}
              step={step.step}
              bills={bills(step.node)}
              onSelect={onSelect}
              headingId={`${route.id}-${step.node}-heading`}
              branch={branches.get(step.node) ?? null}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}

/** A decorative downward connector between two phases of the flow. */
function Junction(): React.JSX.Element {
  return (
    <span className="junction" aria-hidden="true">
      <span className="junction__line" />
      <span className="junction__head" />
    </span>
  );
}

interface RoutePipelineProps {
  readonly route: Route;
  readonly grouped: GroupedBills;
  readonly onSelect: (billId: number) => void;
}

/**
 * One complete route, from introduction to Royal Assent.
 *
 * Below 768px the panel becomes a disclosure so the page stays a single
 * readable sequence; the first route is the one left expanded. At wider
 * widths both routes are always open, because seeing that a Bill can start in
 * either House is part of the explanation.
 */
export function RoutePipeline({ route, grouped, onSelect }: RoutePipelineProps): React.JSX.Element {
  const narrow = useMediaQuery(NARROW_QUERY);
  const defaultOpen = !narrow || route.id === 'commons';
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    setOpen(!narrow || route.id === 'commons');
  }, [narrow, route.id]);

  const total = routeTotal(grouped, route.id);
  const headingId = `route-${route.id}-heading`;

  return (
    <details
      className="route"
      open={open}
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
      }}
    >
      <summary className="route__summary">
        <h2 className="route__title" id={headingId}>
          {route.title}
        </h2>
        <span className="route__count">
          {total} {total === 1 ? 'Bill' : 'Bills'} shown
        </span>
        <span className="route__intro">{route.summary}</span>
      </summary>

      <div className="route__body">
        {route.phases.map((phase, index) => (
          <div key={phase.id}>
            {index === 1 ? (
              // Explanatory marker between the two Houses. It is decorative
              // structure, not a bucket, so it holds no Bills and the rules
              // either side are hidden from assistive technology.
              <p className="transfer">
                <span className="transfer__rule" aria-hidden="true" />
                <span className="transfer__label">{route.transferLabel}</span>
                <span className="transfer__rule" aria-hidden="true" />
                <span className="transfer__rule transfer__rule--head" aria-hidden="true" />
              </p>
            ) : (
              index > 0 && <Junction />
            )}
            <HousePhase
              route={route}
              phase={phase}
              bills={(node) => billsAt(grouped, route.id, node)}
              onSelect={onSelect}
            />
          </div>
        ))}
      </div>
    </details>
  );
}
