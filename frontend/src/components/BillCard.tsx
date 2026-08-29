import { forwardRef } from 'react';
import { formatCalendarDate, formatSourceTimestamp } from '../model/freshness';
import type { Bill } from '../model/types';
import { cardWarnings, warningText } from '../model/warnings';

const HOUSE_LABEL: Record<Bill['currentHouse'], string> = {
  commons: 'Commons',
  lords: 'Lords',
  unassigned: 'Not stated',
};

interface BillCardProps {
  readonly bill: Bill;
  readonly onSelect: (billId: number) => void;
  /** Rendered in the shared ping-pong bucket, where the House matters most. */
  readonly showCurrentHouse?: boolean;
}

/**
 * A compact, focusable summary of one Bill.
 *
 * The visible title is clamped to two lines, but the button's accessible name
 * carries the whole title so it is never truncated for a screen reader.
 *
 * No sponsor portrait, Parliamentary image or other external image appears
 * here or anywhere else in the application.
 */
export const BillCard = forwardRef<HTMLButtonElement, BillCardProps>(function BillCard(
  { bill, onSelect, showCurrentHouse = false },
  ref,
) {
  const warnings = cardWarnings(bill.warnings);
  const nextSitting = bill.stage?.nextSittingDate ?? null;
  const lastUpdate = formatSourceTimestamp(bill.sourceLastUpdate);

  return (
    <button
      type="button"
      ref={ref}
      id={`bill-card-${bill.id}`}
      className={`card card--${bill.originatingHouse}`}
      onClick={() => {
        onSelect(bill.id);
      }}
      aria-label={`${bill.title}. View details.`}
    >
      <span className="card__title" aria-hidden="true">
        {bill.title}
      </span>

      <span className="card__meta">
        {bill.billType !== null && <span className="tag">{bill.billType.name}</span>}

        {showCurrentHouse && bill.currentHouse !== 'unassigned' && (
          <span className={`tag tag--${bill.currentHouse}`}>
            Now in the {HOUSE_LABEL[bill.currentHouse]}
          </span>
        )}

        {bill.pingPongExchangeNumber !== null && (
          <span className="tag tag--accent">Exchange {bill.pingPongExchangeNumber}</span>
        )}

        {bill.carriedOver && <span className="tag">Carried over</span>}

        {warnings.map((code) => (
          <span className="tag tag--warning" key={code}>
            {warningText(code).label}
          </span>
        ))}

        {nextSitting !== null ? (
          <span>Next sitting {formatCalendarDate(nextSitting)}</span>
        ) : (
          lastUpdate !== null && <span>Updated {lastUpdate}</span>
        )}
      </span>
    </button>
  );
});
