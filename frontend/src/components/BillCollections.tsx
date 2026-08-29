import type { Bill } from '../model/types';
import { BillCard } from './BillCard';

interface CollectionProps {
  readonly bills: readonly Bill[];
  readonly onSelect: (billId: number) => void;
}

/**
 * Bills that cannot be placed on either canonical route.
 *
 * These are never discarded. A record this site cannot represent simply is
 * shown here, with the reason on the card, rather than being guessed onto a
 * stage or dropped.
 */
export function SpecialProcedureBills({
  bills,
  onSelect,
}: CollectionProps): React.JSX.Element | null {
  if (bills.length === 0) return null;
  return (
    <section className="section" aria-labelledby="special-heading">
      <h2 className="section__title" id="special-heading">
        Other or special Parliamentary procedure
      </h2>
      <p className="section__intro">
        {bills.length} {bills.length === 1 ? 'Bill is' : 'Bills are'} following a procedure that
        does not map onto the two standard routes, or the source data does not say which House the
        Bill started in. They are listed here rather than being placed by guesswork.
      </p>
      <ul className="section__grid">
        {bills.map((bill) => (
          <li key={bill.id}>
            <BillCard bill={bill} onSelect={onSelect} showCurrentHouse />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Withdrawn and defeated Bills. Acts appear at Royal Assent on the route. */
export function ConcludedBills({ bills, onSelect }: CollectionProps): React.JSX.Element | null {
  if (bills.length === 0) return null;
  return (
    <section className="section" aria-labelledby="concluded-heading">
      <h2 className="section__title" id="concluded-heading">
        No longer progressing
      </h2>
      <p className="section__intro">
        {bills.length} {bills.length === 1 ? 'Bill was' : 'Bills were'} withdrawn or defeated. A
        Bill is only shown as defeated when the source data says so: a Bill that has simply been
        quiet for a long time is still shown as in progress.
      </p>
      <ul className="section__grid">
        {bills.map((bill) => (
          <li key={bill.id}>
            <BillCard bill={bill} onSelect={onSelect} />
          </li>
        ))}
      </ul>
    </section>
  );
}
