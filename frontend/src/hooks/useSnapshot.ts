/**
 * Loading the snapshot, with a cached fallback.
 *
 * The states here are exactly the ones the UI has to distinguish: loading,
 * healthy, stale, served from cache, synthetic example data, and failed.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchSnapshot, readCachedSnapshot, type LoadOutcome } from '../model/load';
import type { InvalidRecord, Snapshot } from '../model/types';

export type SnapshotState =
  | { readonly status: 'loading' }
  | {
      readonly status: 'ready';
      readonly snapshot: Snapshot;
      readonly invalidRecords: readonly InvalidRecord[];
      readonly source: 'network' | 'cache';
      readonly retrievedAt: string;
    }
  | {
      readonly status: 'error';
      readonly reason: 'network' | 'malformed' | 'unsupported-schema';
      readonly message: string;
      readonly schemaVersion?: number;
    };

export interface UseSnapshotResult {
  readonly state: SnapshotState;
  readonly reload: () => void;
}

function toReady(outcome: Extract<LoadOutcome, { kind: 'ok' }>): SnapshotState {
  return {
    status: 'ready',
    snapshot: outcome.snapshot,
    invalidRecords: outcome.invalidRecords,
    source: outcome.source,
    retrievedAt: outcome.retrievedAt,
  };
}

export interface UseSnapshotOptions {
  /** Injected in tests so no test depends on the real network. */
  readonly load?: typeof fetchSnapshot;
  readonly readCache?: typeof readCachedSnapshot;
}

export function useSnapshot(options: UseSnapshotOptions = {}): UseSnapshotResult {
  const load = options.load ?? fetchSnapshot;
  const readCache = options.readCache ?? readCachedSnapshot;
  const [state, setState] = useState<SnapshotState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const optionsRef = useRef({ load, readCache });
  optionsRef.current = { load, readCache };

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    void (async () => {
      const { load: doLoad, readCache: doReadCache } = optionsRef.current;
      let outcome: LoadOutcome;
      try {
        outcome = await doLoad({ signal: controller.signal });
      } catch {
        if (cancelled) return;
        outcome = { kind: 'error', reason: 'network', message: 'The request was interrupted.' };
      }
      if (cancelled) return;

      if (outcome.kind === 'ok') {
        setState(toReady(outcome));
        return;
      }

      // A network failure falls back to the last snapshot this browser saw.
      // A malformed or unsupported document does not: showing older data
      // without saying why would be worse than explaining the problem.
      if (outcome.reason === 'network') {
        const cached = doReadCache();
        if (cached?.kind === 'ok') {
          setState(toReady(cached));
          return;
        }
      }

      setState({
        status: 'error',
        reason: outcome.reason,
        message: outcome.message,
        ...(outcome.schemaVersion === undefined ? {} : { schemaVersion: outcome.schemaVersion }),
      });
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [attempt]);

  const reload = useCallback(() => {
    setState({ status: 'loading' });
    setAttempt((value) => value + 1);
  }, []);

  return { state, reload };
}
