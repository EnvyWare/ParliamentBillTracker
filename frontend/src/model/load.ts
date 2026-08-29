/**
 * Loading the snapshot, and remembering the last good one.
 *
 * The browser only ever talks to its own origin. It never contacts the
 * Parliament API: the ingestion function does that on a schedule and
 * publishes a single static file.
 */

import { parseSnapshot } from './parse';
import type { InvalidRecord, Snapshot } from './types';

export const SNAPSHOT_URL = '/data/current.json';

const CACHE_KEY = 'uk-bill-pipeline:snapshot:v1';

export type LoadSource = 'network' | 'cache';

export type LoadOutcome =
  | {
      readonly kind: 'ok';
      readonly snapshot: Snapshot;
      readonly invalidRecords: readonly InvalidRecord[];
      readonly source: LoadSource;
      /** When this copy was retrieved by the browser, not when it was generated. */
      readonly retrievedAt: string;
    }
  | {
      readonly kind: 'error';
      readonly reason: 'network' | 'malformed' | 'unsupported-schema';
      readonly message: string;
      readonly schemaVersion?: number;
    };

interface CacheEntry {
  readonly retrievedAt: string;
  readonly document: unknown;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    // Private browsing or blocked site data. Caching is a convenience, so a
    // refusal here is not an error.
    return null;
  }
}

export function readCachedSnapshot(): LoadOutcome | null {
  const store = storage();
  if (store === null) return null;

  let entry: CacheEntry;
  try {
    const raw = store.getItem(CACHE_KEY);
    if (raw === null) return null;
    entry = JSON.parse(raw) as CacheEntry;
  } catch {
    return null;
  }

  if (typeof entry?.retrievedAt !== 'string') return null;

  const parsed = parseSnapshot(entry.document);
  if (!parsed.ok) return null;
  return {
    kind: 'ok',
    snapshot: parsed.snapshot,
    invalidRecords: parsed.invalidRecords,
    source: 'cache',
    retrievedAt: entry.retrievedAt,
  };
}

export function writeCachedSnapshot(document: unknown, retrievedAt: string): void {
  const store = storage();
  if (store === null) return;
  try {
    store.setItem(CACHE_KEY, JSON.stringify({ retrievedAt, document } satisfies CacheEntry));
  } catch {
    // A full quota must never break the page.
  }
}

export function clearCachedSnapshot(): void {
  try {
    storage()?.removeItem(CACHE_KEY);
  } catch {
    // Ignored for the same reason as above.
  }
}

export interface FetchOptions {
  readonly signal?: AbortSignal;
  readonly now?: () => Date;
  readonly fetchImpl?: typeof fetch;
}

/**
 * Fetch and parse the published snapshot.
 *
 * A successful, valid result is written to the cache so a later network
 * failure can fall back to it.
 */
export async function fetchSnapshot(options: FetchOptions = {}): Promise<LoadOutcome> {
  const doFetch = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const now = options.now ?? ((): Date => new Date());

  let document: unknown;
  try {
    const response = await doFetch(SNAPSHOT_URL, {
      cache: 'no-cache',
      ...(options.signal ? { signal: options.signal } : {}),
    });
    if (!response.ok) {
      return {
        kind: 'error',
        reason: 'network',
        message: `The data file could not be loaded (HTTP ${response.status}).`,
      };
    }
    document = await response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    return {
      kind: 'error',
      reason: 'network',
      message: 'The data file could not be loaded. You may be offline.',
    };
  }

  const parsed = parseSnapshot(document);
  if (!parsed.ok) {
    return {
      kind: 'error',
      reason: parsed.reason,
      message: parsed.message,
      ...(parsed.schemaVersion === undefined ? {} : { schemaVersion: parsed.schemaVersion }),
    };
  }

  const retrievedAt = now().toISOString();
  writeCachedSnapshot(document, retrievedAt);
  return {
    kind: 'ok',
    snapshot: parsed.snapshot,
    invalidRecords: parsed.invalidRecords,
    source: 'network',
    retrievedAt,
  };
}
