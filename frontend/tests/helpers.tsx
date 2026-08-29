import { render, type RenderResult } from '@testing-library/react';
import { App } from '../src/App';
import type { LoadOutcome } from '../src/model/load';
import { parseSnapshot } from '../src/model/parse';
import type { Bill, Snapshot } from '../src/model/types';
import exampleDocument from '../public/data/current.json';

/** The checked-in synthetic snapshot, as raw JSON. */
export const EXAMPLE_DOCUMENT: unknown = exampleDocument;

/** A deep clone, so a test can mutate the document without affecting others. */
export function cloneDocument(): Record<string, unknown> {
  return structuredClone(EXAMPLE_DOCUMENT) as Record<string, unknown>;
}

export function exampleSnapshot(): Snapshot {
  const parsed = parseSnapshot(EXAMPLE_DOCUMENT);
  if (!parsed.ok) throw new Error(`The example snapshot did not parse: ${parsed.message}`);
  return parsed.snapshot;
}

export function billById(id: number): Bill {
  const bill = exampleSnapshot().bills.find((candidate) => candidate.id === id);
  if (bill === undefined) throw new Error(`No example Bill with id ${id}`);
  return bill;
}

/** Fixed instant used wherever the tests need a clock. */
export const TEST_NOW = new Date('2026-08-29T13:00:00Z');

export function okOutcome(
  document: unknown = EXAMPLE_DOCUMENT,
  source: 'network' | 'cache' = 'network',
): LoadOutcome {
  const parsed = parseSnapshot(document);
  if (!parsed.ok) throw new Error(`Test document did not parse: ${parsed.message}`);
  return {
    kind: 'ok',
    snapshot: parsed.snapshot,
    invalidRecords: parsed.invalidRecords,
    source,
    retrievedAt: TEST_NOW.toISOString(),
  };
}

/**
 * Map a document to the outcome the real loader would produce, including the
 * failure outcomes, so a test can exercise an unsupported or malformed file.
 */
export function outcomeFor(document: unknown): LoadOutcome {
  const parsed = parseSnapshot(document);
  if (!parsed.ok) {
    return {
      kind: 'error',
      reason: parsed.reason,
      message: parsed.message,
      ...(parsed.schemaVersion === undefined ? {} : { schemaVersion: parsed.schemaVersion }),
    };
  }
  return {
    kind: 'ok',
    snapshot: parsed.snapshot,
    invalidRecords: parsed.invalidRecords,
    source: 'network',
    retrievedAt: TEST_NOW.toISOString(),
  };
}

export interface RenderAppOptions {
  readonly document?: unknown;
  readonly load?: () => Promise<LoadOutcome>;
  readonly readCache?: () => LoadOutcome | null;
  readonly now?: Date;
  /** Query string to start at, e.g. "?bill=9004". */
  readonly search?: string;
}

export function renderApp(options: RenderAppOptions = {}): RenderResult {
  if (options.search !== undefined) {
    window.history.replaceState(null, '', `/${options.search}`);
  }
  const load =
    options.load ??
    ((): Promise<LoadOutcome> => Promise.resolve(outcomeFor(options.document ?? EXAMPLE_DOCUMENT)));
  return render(
    <App
      snapshotOptions={{
        load,
        ...(options.readCache ? { readCache: options.readCache } : { readCache: () => null }),
      }}
      now={options.now ?? TEST_NOW}
    />,
  );
}
