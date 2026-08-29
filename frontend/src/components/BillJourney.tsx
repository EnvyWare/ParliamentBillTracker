import { formatCalendarDate, formatSourceTimestamp } from '../model/freshness';
import { ANYTIME_OUTCOMES, NODE_INFO } from '../model/routes';
import type { Bill, HistoryEntry, House } from '../model/types';
import { warningText } from '../model/warnings';
import {
  STEP_STATE_DESCRIPTION,
  STEP_STATE_LABEL,
  buildJourney,
  type JourneyStep,
  type StepState,
} from '../selectors/journey';
import { BillFlowDiagram } from './BillFlowDiagram';

const HOUSE_LABEL: Record<House, string> = {
  commons: 'House of Commons',
  lords: 'House of Lords',
  unassigned: 'Not stated',
};

/** A short mark for each state. Never the only signal: the label sits beside it. */
const STATE_MARK: Record<StepState, string> = {
  completed: '✓',
  current: '●',
  upcoming: '○',
  skipped: '–',
  stopped: '✕',
};

/**
 * A decision between two steps.
 *
 * Rendered as a diamond in the flow, with each outcome shown as its own
 * branch. Where the record settles which way this Bill went, that branch is
 * marked as taken and the other is dimmed; where it does not, both are shown
 * neutrally rather than guessing.
 */
interface BillJourneyProps {
  readonly bill: Bill;
  readonly onBack: () => void;
}

function sittingDates(entry: HistoryEntry): string {
  const dates = entry.sittings
    .map((sitting) => sitting.date)
    .filter((date): date is string => date !== null);
  return dates.length === 0 ? '' : dates.map(formatCalendarDate).join(', ');
}

function StepNode({ step }: { readonly step: JourneyStep }): React.JSX.Element {
  const info = NODE_INFO[step.node];
  return (
    <section className={`bucket node node--${step.state}`} aria-labelledby={`journey-${step.node}`}>
      <div className="bucket__header">
        <h4 className="bucket__name" id={`journey-${step.node}`}>
          <span className="bucket__step" aria-hidden="true">
            {step.step}
          </span>
          <span className="visually-hidden">Step {step.step}: </span>
          {info.label}
        </h4>
        <span className={`node__state node__state--${step.state}`}>
          <span aria-hidden="true">{STATE_MARK[step.state]}</span> {STEP_STATE_LABEL[step.state]}
        </span>
      </div>

      <div className="node__body">
        <p className="node__meaning">{STEP_STATE_DESCRIPTION[step.state]}</p>

        {step.occurrences.length > 0 && (
          <ul className="node__events">
            {step.occurrences.map((entry, index) => (
              <li key={`${entry.billStageId ?? index}`}>
                <span className="node__event-name">{entry.label}</span>
                {sittingDates(entry) !== '' && (
                  <span className="node__event-date"> · {sittingDates(entry)}</span>
                )}
              </li>
            ))}
          </ul>
        )}

        {step.sideEvents.length > 0 && (
          <div className="node__side">
            <p className="node__side-title">Alongside this stage</p>
            <ul className="node__events">
              {step.sideEvents.map((entry, index) => (
                <li key={`${entry.billStageId ?? index}`}>
                  <span className="node__event-name">{entry.label}</span>
                  {sittingDates(entry) !== '' && (
                    <span className="node__event-date"> · {sittingDates(entry)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

/**
 * One Bill's route, with the path it has actually taken marked on it.
 *
 * Every stage stays visible, including the ones the Bill has not reached, so
 * the reader can see how far through the process this Bill is rather than
 * only what has already happened. A stage with no recorded sitting is marked
 * as not recorded rather than being drawn as completed.
 */
export function BillJourney({ bill, onBack }: BillJourneyProps): React.JSX.Element {
  const journey = buildJourney(bill);

  return (
    <div className="shell journey">
      <nav aria-label="Breadcrumb">
        <button type="button" className="button button--quiet journey__back" onClick={onBack}>
          <span aria-hidden="true">&larr;</span> Back to all Bills
        </button>
      </nav>

      <header className="journey__header">
        <h2 className="journey__title">{bill.title}</h2>
        <p className="journey__summary">
          {bill.summary ?? 'No summary is published for this Bill.'}
        </p>

        <dl className="journey__facts">
          <div>
            <dt>Status</dt>
            <dd>{describeStatus(bill)}</dd>
          </div>
          <div>
            <dt>Started in</dt>
            <dd>{HOUSE_LABEL[bill.originatingHouse]}</dd>
          </div>
          <div>
            <dt>Currently in</dt>
            <dd>{HOUSE_LABEL[bill.currentHouse]}</dd>
          </div>
          {bill.billType !== null && (
            <div>
              <dt>Type</dt>
              <dd>{bill.billType.name}</dd>
            </div>
          )}
          <div>
            <dt>Progress</dt>
            <dd>
              {journey.completedCount} of {journey.totalCount} stages completed
            </dd>
          </div>
          {formatSourceTimestamp(bill.sourceLastUpdate) !== null && (
            <div>
              <dt>Source last updated</dt>
              <dd>{formatSourceTimestamp(bill.sourceLastUpdate)}</dd>
            </div>
          )}
        </dl>

        {bill.warnings.length > 0 && (
          <ul className="journey__warnings">
            {bill.warnings.map((code) => (
              <li key={code}>
                <strong>{warningText(code).label}.</strong> {warningText(code).description}
              </li>
            ))}
          </ul>
        )}
      </header>

      {journey.route === null ? (
        <div className="no-results">
          <h3 className="section__title">This Bill cannot be placed on a standard route</h3>
          <p className="section__intro">
            The source data does not say which House this Bill started in, so there is no route to
            draw it against. Its recorded stages are listed below instead.
          </p>
          <ul className="node__events journey__fallback">
            {bill.history.map((entry, index) => (
              <li key={`${entry.billStageId ?? index}`}>
                <span className="node__event-name">{entry.label}</span>
                {sittingDates(entry) !== '' && (
                  <span className="node__event-date"> · {sittingDates(entry)}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          <section className="journey__flow" aria-labelledby="journey-route-heading">
            <h3 className="journey__route-title" id="journey-route-heading">
              {journey.route.title}
            </h3>

            <BillFlowDiagram bill={bill} journey={journey} />

            <div className="flow-legend">
              <h4 className="flow-legend__title">How to read this</h4>
              <ul>
                {(['completed', 'current', 'skipped', 'upcoming'] as const).map((state) => (
                  <li key={state}>
                    <span
                      className={`flow-legend__swatch flow-legend__swatch--${state}`}
                      aria-hidden="true"
                    />
                    {STEP_STATE_LABEL[state]}
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="section" aria-labelledby="journey-detail-heading">
            <h3 className="section__title" id="journey-detail-heading">
              Stage by stage
            </h3>
            <p className="section__intro">
              What the source data records at each stage of this Bill&rsquo;s route, including the
              procedural stages that ran alongside it.
            </p>
            <ol className="journey__steps">
              {journey.steps.map((step) => (
                <li key={step.node}>
                  <StepNode step={step} />
                </li>
              ))}
            </ol>
          </section>
        </>
      )}

      {journey.route !== null && (
        <section className="section" aria-labelledby="journey-anytime">
          <h3 className="section__title" id="journey-anytime">
            Ways a Bill can end early
          </h3>
          <p className="section__intro">
            These are not steps on the route. They can happen at any point, which is why they are
            listed separately rather than drawn into the flow.
          </p>
          <ul className="journey__anytime">
            {ANYTIME_OUTCOMES.map((outcome) => (
              <li key={outcome.title}>
                <strong>{outcome.title}.</strong> {outcome.detail}
              </li>
            ))}
          </ul>
        </section>
      )}

      {journey.unplacedEvents.length > 0 && (
        <section className="section" aria-labelledby="journey-unplaced">
          <h3 className="section__title" id="journey-unplaced">
            Before the Bill reached a main stage
          </h3>
          <ul className="node__events">
            {journey.unplacedEvents.map((entry, index) => (
              <li key={`${entry.billStageId ?? index}`}>
                <span className="node__event-name">{entry.label}</span>
                {sittingDates(entry) !== '' && (
                  <span className="node__event-date"> · {sittingDates(entry)}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="journey__external">
        <a
          className="external-link"
          href={bill.parliamentUrl}
          rel="noopener noreferrer"
          target="_blank"
        >
          View on UK Parliament
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      </p>
    </div>
  );
}

function describeStatus(bill: Bill): string {
  switch (bill.status) {
    case 'active':
      return 'In progress';
    case 'enacted':
      return 'Received Royal Assent and is now an Act of Parliament';
    case 'withdrawn':
      return 'Withdrawn';
    case 'failed':
      return 'Defeated in a vote';
    case 'unknown':
      return 'Not known from the source data';
  }
}
