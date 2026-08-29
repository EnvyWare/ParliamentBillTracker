import { formatRelative, formatUkDateTime, parseGeneratedAt } from '../model/freshness';
import type { Snapshot } from '../model/types';

interface AppHeaderProps {
  readonly snapshot: Snapshot | null;
  /** Bills matching the current filters, for the visible count. */
  readonly visibleCount: number | null;
  readonly now: Date;
}

/**
 * Compact identity bar.
 *
 * The unofficial badge sits directly beside the product name, and is never
 * conditional: this project must never look like an official service.
 */
export function AppHeader({ snapshot, visibleCount, now }: AppHeaderProps): React.JSX.Element {
  const generated = snapshot === null ? null : parseGeneratedAt(snapshot.generatedAt);

  return (
    <header className="header">
      <div className="shell header__inner">
        <div className="header__identity">
          <h1 className="header__title">
            <span className="header__mark" aria-hidden="true" />
            UK Bill Pipeline
          </h1>
          <span className="badge-unofficial">Unofficial project</span>
        </div>

        <p className="header__meta">
          {snapshot !== null && (
            <span>
              Session <strong>{snapshot.source.sessionLabel}</strong>
            </span>
          )}
          {visibleCount !== null && (
            <span>
              <strong>{visibleCount}</strong> {visibleCount === 1 ? 'Bill' : 'Bills'} shown
            </span>
          )}
          {snapshot !== null && (
            <span>
              {snapshot.synthetic ? (
                <>
                  Example data, generated{' '}
                  {generated === null ? 'at an unknown time' : formatUkDateTime(generated)}
                </>
              ) : generated === null ? (
                'Retrieval time unavailable'
              ) : (
                <>
                  Retrieved {formatRelative(generated, now)}
                  {' · '}
                  <time dateTime={snapshot.generatedAt}>{formatUkDateTime(generated)}</time>
                </>
              )}
            </span>
          )}
        </p>
      </div>
    </header>
  );
}
