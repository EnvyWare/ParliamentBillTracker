import { formatRelative, isStale, parseGeneratedAt } from '../model/freshness';
import type { InvalidRecord, Snapshot } from '../model/types';

interface DataStatusBannerProps {
  readonly snapshot: Snapshot;
  readonly source: 'network' | 'cache';
  readonly retrievedAt: string;
  readonly invalidRecords: readonly InvalidRecord[];
  readonly now: Date;
}

/**
 * Non-blocking notices about the data itself.
 *
 * None of these hide the Bills. A reader is always better served by seeing
 * the data plus an honest caveat than by seeing nothing.
 */
export function DataStatusBanner({
  snapshot,
  source,
  retrievedAt,
  invalidRecords,
  now,
}: DataStatusBannerProps): React.JSX.Element | null {
  const generated = parseGeneratedAt(snapshot.generatedAt);
  const stale = isStale(snapshot, now);
  const cachedAt = new Date(retrievedAt);
  const banners: React.JSX.Element[] = [];

  if (snapshot.synthetic) {
    banners.push(
      <p className="banner banner--info" key="synthetic">
        <span className="banner__label">Example data</span>
        <span>
          These are invented Bills used for local development. They do not describe any real Bill
          before the UK Parliament.
        </span>
      </p>,
    );
  }

  if (source === 'cache') {
    banners.push(
      <p className="banner banner--warning" key="cache">
        <span className="banner__label">Cached data</span>
        <span>
          The live data could not be loaded, so this is the copy your browser saved
          {Number.isNaN(cachedAt.getTime()) ? '' : ` ${formatRelative(cachedAt, now)}`}. It may be
          out of date.
        </span>
      </p>,
    );
  }

  if (stale && source !== 'cache') {
    banners.push(
      <p className="banner banner--warning" key="stale">
        <span className="banner__label">Data may be out of date</span>
        <span>
          This snapshot was published
          {generated === null ? ' at an unknown time' : ` ${formatRelative(generated, now)}`} and
          should refresh every 30 minutes. The Bills below are still shown.
        </span>
      </p>,
    );
  }

  for (const warning of snapshot.warnings) {
    if (warning.code === 'synthetic_example_data') continue;
    banners.push(
      <p
        className={`banner banner--${warning.severity === 'error' ? 'error' : warning.severity === 'info' ? 'info' : 'warning'}`}
        key={`warning-${warning.code}`}
      >
        <span className="banner__label">
          {warning.severity === 'info' ? 'Note' : 'Data warning'}
        </span>
        <span>{warning.message}</span>
      </p>,
    );
  }

  if (invalidRecords.length > 0) {
    banners.push(
      <p className="banner banner--warning" key="invalid">
        <span className="banner__label">
          {invalidRecords.length} record{invalidRecords.length === 1 ? '' : 's'} could not be read
        </span>
        <span>
          Part of the data file could not be understood and has been left out. Everything else is
          shown normally.
        </span>
      </p>,
    );
  }

  if (banners.length === 0) return null;
  return <div className="shell">{banners}</div>;
}
