/** Parsing, freshness and URL state. */

import { describe, expect, it } from 'vitest';
import {
  formatCalendarDate,
  formatRelative,
  formatSourceTimestamp,
  formatUkDateTime,
  isStale,
  parseGeneratedAt,
} from '../src/model/freshness';
import { parseSnapshot } from '../src/model/parse';
import type { Snapshot } from '../src/model/types';
import { DEFAULT_FILTERS } from '../src/selectors/filters';
import { parseViewState, serialiseViewState } from '../src/selectors/urlState';
import { EXAMPLE_DOCUMENT, cloneDocument, exampleSnapshot } from './helpers';

describe('parsing', () => {
  it('accepts the example snapshot with no invalid records', () => {
    const result = parseSnapshot(EXAMPLE_DOCUMENT);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.invalidRecords).toEqual([]);
    expect(result.snapshot.bills.length).toBeGreaterThan(0);
  });

  it('explains an unsupported schema version instead of guessing', () => {
    const document = cloneDocument();
    document['schemaVersion'] = 2;
    const result = parseSnapshot(document);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toBe('unsupported-schema');
    expect(result.schemaVersion).toBe(2);
    expect(result.message).toContain('schema 2');
  });

  it('isolates one malformed Bill and keeps the rest', () => {
    const document = cloneDocument();
    const bills = document['bills'] as Record<string, unknown>[];
    const originalCount = bills.length;
    bills[2] = { id: 'not a number' };

    const result = parseSnapshot(document);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.snapshot.bills).toHaveLength(originalCount - 1);
    expect(result.invalidRecords).toHaveLength(1);
    expect(result.invalidRecords[0]?.index).toBe(2);
  });

  it('isolates a record whose enum value is unrecognised', () => {
    const document = cloneDocument();
    (document['bills'] as Record<string, unknown>[])[0]!['originatingHouse'] = 'Commons';
    const result = parseSnapshot(document);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.invalidRecords).toHaveLength(1);
  });

  it('rejects a document that is not an object', () => {
    expect(parseSnapshot('nope').ok).toBe(false);
    expect(parseSnapshot(null).ok).toBe(false);
    expect(parseSnapshot([1, 2, 3]).ok).toBe(false);
  });

  it('rejects a document with no schema version', () => {
    const document = cloneDocument();
    delete document['schemaVersion'];
    const result = parseSnapshot(document);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toBe('malformed');
  });

  it('rejects a document missing its source block', () => {
    const document = cloneDocument();
    delete document['source'];
    expect(parseSnapshot(document).ok).toBe(false);
  });

  it('keeps the raw stage label alongside the normalised node', () => {
    const bill = exampleSnapshot().bills.find((candidate) => candidate.id === 9019);
    expect(bill?.pipelineNode).toBe('unknown');
    expect(bill?.stage?.detail).toBe('A stage introduced after this build');
  });
});

describe('freshness', () => {
  const now = new Date('2026-08-29T13:00:00Z');

  function snapshotAt(generatedAt: string, synthetic = false): Snapshot {
    return { ...exampleSnapshot(), generatedAt, synthetic };
  }

  it('parses only a properly formed UTC timestamp', () => {
    expect(parseGeneratedAt('2026-08-29T12:00:00Z')).toBeInstanceOf(Date);
    expect(parseGeneratedAt('2026-08-29T12:00:00')).toBeNull();
    expect(parseGeneratedAt('nonsense')).toBeNull();
  });

  it('treats a live snapshot older than three hours as stale', () => {
    expect(isStale(snapshotAt('2026-08-29T12:00:00Z'), now)).toBe(false);
    expect(isStale(snapshotAt('2026-08-29T09:30:00Z'), now)).toBe(true);
  });

  it('never calls the example snapshot stale', () => {
    // Its timestamp is a fixed constant so the checked-in file stays
    // reproducible; measuring its age would say nothing useful.
    expect(isStale(snapshotAt('2020-01-01T00:00:00Z', true), now)).toBe(false);
  });

  it('treats an unreadable timestamp as stale', () => {
    expect(isStale(snapshotAt('not a time'), now)).toBe(true);
  });

  it('describes recent times in plain words', () => {
    expect(formatRelative(new Date('2026-08-29T12:48:00Z'), now)).toBe('12 minutes ago');
    expect(formatRelative(new Date('2026-08-29T12:59:30Z'), now)).toBe('just now');
    expect(formatRelative(new Date('2026-08-29T12:00:00Z'), now)).toBe('1 hour ago');
    expect(formatRelative(new Date('2026-08-27T13:00:00Z'), now)).toBe('2 days ago');
  });

  it('shows absolute times in UK time with the zone named', () => {
    // 12:00 UTC in August is 13:00 British Summer Time.
    expect(formatUkDateTime(new Date('2026-08-29T12:00:00Z'))).toBe('29 August 2026, 13:00 BST');
    expect(formatUkDateTime(new Date('2026-01-15T12:00:00Z'))).toBe('15 January 2026, 12:00 GMT');
  });

  it('renders a calendar date without shifting it across a time zone', () => {
    expect(formatCalendarDate('2026-09-07')).toBe('7 September 2026');
    expect(formatCalendarDate('2026-01-01')).toBe('1 January 2026');
  });

  it('shows only the date part of an offset-free source timestamp', () => {
    expect(formatSourceTimestamp('2026-08-28T18:42:57.9656298')).toBe('28 August 2026');
    expect(formatSourceTimestamp(null)).toBeNull();
    expect(formatSourceTimestamp('rubbish')).toBeNull();
  });
});

describe('URL state', () => {
  it('omits defaults so a shared link stays short', () => {
    expect(
      serialiseViewState({ filters: DEFAULT_FILTERS, selectedBillId: null, billView: 'summary' }),
    ).toBe('');
  });

  it('round-trips every filter and the selected Bill', () => {
    const view = {
      filters: {
        search: 'health',
        status: 'all' as const,
        originatingHouse: 'lords' as const,
        currentHouse: 'commons' as const,
        stage: 'lords_committee' as const,
        billType: 'Government Bill',
      },
      selectedBillId: 9004,
      billView: 'journey' as const,
    };
    const query = serialiseViewState(view);
    expect(parseViewState(query)).toEqual(view);
  });

  it('defaults a selected Bill to the summary sheet', () => {
    expect(parseViewState('?bill=9004').billView).toBe('summary');
    expect(parseViewState('?bill=9004&view=journey').billView).toBe('journey');
    expect(parseViewState('?bill=9004&view=nonsense').billView).toBe('summary');
  });

  it('omits the view parameter when no Bill is selected', () => {
    expect(
      serialiseViewState({ filters: DEFAULT_FILTERS, selectedBillId: null, billView: 'journey' }),
    ).toBe('');
  });

  it('ignores values it does not recognise rather than failing', () => {
    const view = parseViewState('?status=sideways&origin=moon&stage=nowhere&bill=abc');
    expect(view.filters.status).toBe('in_progress');
    expect(view.filters.originatingHouse).toBeNull();
    expect(view.filters.stage).toBeNull();
    expect(view.selectedBillId).toBeNull();
  });

  it('reads a bare bill parameter', () => {
    expect(parseViewState('?bill=9004').selectedBillId).toBe(9004);
  });
});
