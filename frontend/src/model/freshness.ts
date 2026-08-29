/**
 * How old the data is, expressed in UK time.
 *
 * Only `generatedAt` is a real instant: the ingestion function produces it in
 * UTC. Source timestamps carry no offset and are never treated as instants.
 */

import type { Snapshot } from './types';

/** Beyond this, a live snapshot is shown with a non-blocking stale warning. */
export const STALE_AFTER_MINUTES = 180;

const UK_TIME_ZONE = 'Europe/London';

export function parseGeneratedAt(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(value)) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function ageInMinutes(snapshot: Snapshot, now: Date): number | null {
  const generated = parseGeneratedAt(snapshot.generatedAt);
  if (generated === null) return null;
  return (now.getTime() - generated.getTime()) / 60_000;
}

/**
 * Whether a live snapshot is old enough to warn about.
 *
 * The synthetic example snapshot is excluded. Its timestamp is a fixed
 * constant so the checked-in file stays reproducible, so measuring its age
 * would tell the reader nothing except that the constant is in the past.
 */
export function isStale(
  snapshot: Snapshot,
  now: Date,
  thresholdMinutes = STALE_AFTER_MINUTES,
): boolean {
  if (snapshot.synthetic) return false;
  const age = ageInMinutes(snapshot, now);
  return age === null || age > thresholdMinutes;
}

/** "12 minutes ago", "3 hours ago", "just now". */
export function formatRelative(from: Date, now: Date): string {
  const seconds = Math.round((now.getTime() - from.getTime()) / 1000);
  if (seconds < 0) return 'just now';
  if (seconds < 60) return 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} ${plural(minutes, 'minute')} ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${plural(hours, 'hour')} ago`;

  const days = Math.floor(hours / 24);
  return `${days} ${plural(days, 'day')} ago`;
}

function plural(count: number, word: string): string {
  return count === 1 ? word : `${word}s`;
}

/** "29 August 2026, 13:00 BST" — always UK time, with the zone named. */
export function formatUkDateTime(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: UK_TIME_ZONE,
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  }).formatToParts(date);

  const value = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((part) => part.type === type)?.value ?? '';

  return (
    `${value('day')} ${value('month')} ${value('year')}, ` +
    `${value('hour')}:${value('minute')} ${value('timeZoneName')}`
  );
}

/** "7 September 2026" — a Parliamentary calendar date, with no time or zone. */
export function formatCalendarDate(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return isoDate;
  const [, year, month, day] = match;
  // Constructed as UTC and formatted as UTC: this is a calendar date, so it
  // must not be shifted by a time zone on the way to the screen.
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(date);
}

/**
 * Render a source timestamp that carries no offset.
 *
 * The date part is shown and the time part discarded, because the source does
 * not say what zone the time is in and inventing one would be a lie.
 */
export function formatSourceTimestamp(value: string | null): string | null {
  if (value === null) return null;
  const datePart = value.split('T')[0] ?? '';
  return /^\d{4}-\d{2}-\d{2}$/.test(datePart) ? formatCalendarDate(datePart) : null;
}
