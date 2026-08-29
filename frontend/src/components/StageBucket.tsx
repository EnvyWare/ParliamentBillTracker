import { NODE_INFO, type BranchPoint } from '../model/routes';
import type { Bill, PipelineNode } from '../model/types';
import { BillCard } from './BillCard';

interface StageBucketProps {
  readonly node: PipelineNode;
  /** Position in the legislative sequence for the route this bucket is in. */
  readonly step: number;
  readonly bills: readonly Bill[];
  readonly onSelect: (billId: number) => void;
  readonly headingId: string;
  /** The decision that follows this stage, if there is one. */
  readonly branch?: BranchPoint | null;
}

/**
 * One stage of a route.
 *
 * The bucket stays visible with a zero count when nothing is in it: an empty
 * stage is part of the explanation of the process, not noise to be hidden.
 * The bucket itself is never coloured as complete or incomplete, because
 * completion is a property of a Bill rather than of a stage.
 */
export function StageBucket({
  node,
  step,
  bills,
  onSelect,
  headingId,
  branch = null,
}: StageBucketProps): React.JSX.Element {
  const info = NODE_INFO[node];
  const isPingPong = node === 'ping_pong';

  return (
    <section className="bucket" aria-labelledby={headingId}>
      <div className="bucket__header">
        <h4 className="bucket__name" id={headingId}>
          <span className="bucket__step" aria-hidden="true">
            {step}
          </span>
          <span className="visually-hidden">Step {step}: </span>
          {info.label}
        </h4>
        <span className="bucket__count">
          {bills.length} {bills.length === 1 ? 'Bill' : 'Bills'}
        </span>
        <p className="bucket__explanation">{info.explanation}</p>
        {isPingPong && (
          <span className="bucket__loop">
            This step repeats until both Houses agree the same text.
          </span>
        )}
      </div>

      {branch !== null && (
        // The route is not a straight line. This names the decision that
        // follows the stage and what happens if it goes the other way, so the
        // chart does not imply every Bill simply walks to the end.
        <p className="bucket__branch">
          <span className="bucket__branch-question">{branch.question}</span>
          {branch.outcomes
            .filter((outcome) => outcome.kind !== 'continue')
            .map((outcome) => (
              <span className="bucket__branch-outcome" key={outcome.answer}>
                <strong>{outcome.answer}:</strong> {outcome.consequence}
              </span>
            ))}
        </p>
      )}

      {bills.length === 0 ? (
        <p className="bucket__empty">No Bills at this stage.</p>
      ) : (
        <ul className="bucket__list">
          {bills.map((bill) => (
            <li key={bill.id}>
              <BillCard bill={bill} onSelect={onSelect} showCurrentHouse={isPingPong} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
