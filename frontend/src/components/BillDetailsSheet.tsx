import { useEffect, useId, useRef } from 'react';
import { formatCalendarDate, formatSourceTimestamp } from '../model/freshness';
import { NODE_INFO } from '../model/routes';
import type { Bill, House } from '../model/types';
import { warningText } from '../model/warnings';

const HOUSE_LABEL: Record<House, string> = {
  commons: 'House of Commons',
  lords: 'House of Lords',
  unassigned: 'Not stated',
};

const FOCUSABLE =
  'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

interface BillDetailsSheetProps {
  readonly bill: Bill;
  readonly onClose: () => void;
  readonly onViewJourney: () => void;
}

/**
 * Everything known about one Bill.
 *
 * All of it comes from the snapshot that is already loaded: opening a Bill
 * makes no further network request of any kind.
 */
export function BillDetailsSheet({
  bill,
  onClose,
  onViewJourney,
}: BillDetailsSheetProps): React.JSX.Element {
  const ids = useId();
  const sheetRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, [bill.id]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      // Focus stays inside the sheet while it is open.
      const sheet = sheetRef.current;
      if (sheet === null) return;
      const focusable = [...sheet.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => element.offsetParent !== null || element === document.activeElement,
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (first === undefined || last === undefined) return;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
    };
  }, [onClose]);

  const stageLabel = NODE_INFO[bill.pipelineNode].label;
  const lastUpdate = formatSourceTimestamp(bill.sourceLastUpdate);
  const withdrawnOn = formatSourceTimestamp(bill.withdrawnSourceDate);

  return (
    <>
      <div
        className="sheet-backdrop"
        onClick={onClose}
        role="presentation"
        data-testid="sheet-backdrop"
      />
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${ids}-title`}
        ref={sheetRef}
      >
        <div className="sheet__header">
          <h2 className="sheet__title" id={`${ids}-title`}>
            {bill.title}
          </h2>
          <button
            type="button"
            className="sheet__close"
            ref={closeRef}
            onClick={onClose}
            aria-label="Close Bill details"
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>

        <div className="sheet__body">
          <p>
            <button type="button" className="button" onClick={onViewJourney}>
              See this Bill&rsquo;s path through Parliament
            </button>
          </p>

          {bill.summary !== null && (
            <section className="detail-group">
              <h3 className="detail-group__title">Summary</h3>
              <p>{bill.summary}</p>
            </section>
          )}

          <section className="detail-group">
            <h3 className="detail-group__title">Where it is now</h3>
            <dl className="detail-list">
              <dt>Stage on this chart</dt>
              <dd>{stageLabel}</dd>

              {bill.stage !== null && (
                <>
                  <dt>Official stage name</dt>
                  <dd>{bill.stage.detail ?? bill.stage.label}</dd>
                </>
              )}

              <dt>Status</dt>
              <dd>{describeStatus(bill)}</dd>

              {bill.pingPongExchangeNumber !== null && (
                <>
                  <dt>Ping-pong</dt>
                  <dd>
                    Exchange {bill.pingPongExchangeNumber} — the Houses are still agreeing the final
                    wording.
                  </dd>
                </>
              )}

              {bill.stage?.nextSittingDate != null && (
                <>
                  <dt>Next sitting</dt>
                  <dd>{formatCalendarDate(bill.stage.nextSittingDate)}</dd>
                </>
              )}

              {lastUpdate !== null && (
                <>
                  <dt>Source last updated</dt>
                  <dd>{lastUpdate}</dd>
                </>
              )}

              {withdrawnOn !== null && (
                <>
                  <dt>Withdrawn</dt>
                  <dd>{withdrawnOn}</dd>
                </>
              )}
            </dl>
          </section>

          <section className="detail-group">
            <h3 className="detail-group__title">About this Bill</h3>
            <dl className="detail-list">
              {bill.formerTitle !== null && (
                <>
                  <dt>Former title</dt>
                  <dd>{bill.formerTitle}</dd>
                </>
              )}

              {bill.billType !== null && (
                <>
                  <dt>Type</dt>
                  <dd>
                    {bill.billType.name}
                    {bill.billType.category !== null && ` (${bill.billType.category})`}
                  </dd>
                </>
              )}

              <dt>Starts in</dt>
              <dd>{HOUSE_LABEL[bill.originatingHouse]}</dd>

              <dt>Currently in</dt>
              <dd>{HOUSE_LABEL[bill.currentHouse]}</dd>

              {bill.carriedOver && (
                <>
                  <dt>Carried over</dt>
                  <dd>
                    This Bill was introduced in an earlier session and carried over into the current
                    one.
                  </dd>
                </>
              )}

              {bill.sponsors.length > 0 && (
                <>
                  <dt>{bill.sponsors.length === 1 ? 'Sponsor' : 'Sponsors'}</dt>
                  <dd>
                    <ul>
                      {bill.sponsors.map((sponsor, index) => (
                        <li key={`${sponsor.memberId ?? 'org'}-${index}`}>
                          {sponsor.name}
                          {sponsor.party !== null && ` — ${sponsor.party}`}
                          {sponsor.organisation !== null && ` (${sponsor.organisation})`}
                        </li>
                      ))}
                    </ul>
                  </dd>
                </>
              )}
            </dl>
          </section>

          {bill.warnings.length > 0 && (
            <section className="detail-group">
              <h3 className="detail-group__title">Things to be aware of</h3>
              <ul>
                {bill.warnings.map((code) => (
                  <li key={code}>
                    <strong>{warningText(code).label}.</strong> {warningText(code).description}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="detail-group">
            <h3 className="detail-group__title">
              Stage history
              {!bill.historyComplete && ' (incomplete)'}
            </h3>
            {bill.history.length === 0 ? (
              <p>No stage history is available for this Bill.</p>
            ) : (
              <ol className="timeline">
                {bill.history.map((entry, index) => (
                  <li
                    className={`timeline__item timeline__item--${entry.house}`}
                    key={`${entry.billStageId ?? index}`}
                  >
                    {entry.label}
                    <span className="timeline__meta">
                      {entry.house === 'unassigned' ? 'Both Houses' : HOUSE_LABEL[entry.house]}
                      {entry.sittings.length > 0 &&
                        ` · ${entry.sittings
                          .map((sitting) =>
                            sitting.date === null
                              ? 'date unknown'
                              : formatCalendarDate(sitting.date),
                          )
                          .join(', ')}`}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <p>
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
      </div>
    </>
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
