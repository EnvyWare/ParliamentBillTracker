/**
 * Narrow an untrusted JSON document into a typed {@link Snapshot}.
 *
 * Two rules shape this module:
 *
 * - An unsupported `schemaVersion` is an explicit, explained failure. It is
 *   never partially interpreted.
 * - A single malformed Bill is isolated and reported, never allowed to take
 *   the rest of the snapshot down with it.
 */

import {
  BILL_STATUSES,
  HOUSES,
  MAPPING_MODES,
  PIPELINE_NODES,
  SUPPORTED_SCHEMA_VERSION,
  type Bill,
  type BillStatus,
  type BillType,
  type HistoryEntry,
  type House,
  type InvalidRecord,
  type MappingMode,
  type PipelineNode,
  type Sitting,
  type Snapshot,
  type SnapshotCounts,
  type SnapshotSource,
  type SnapshotWarning,
  type Sponsor,
  type StageOccurrence,
} from './types';

export type ParseFailureReason = 'unsupported-schema' | 'malformed';

export type ParseResult =
  | { readonly ok: true; readonly snapshot: Snapshot; readonly invalidRecords: InvalidRecord[] }
  | {
      readonly ok: false;
      readonly reason: ParseFailureReason;
      readonly message: string;
      readonly schemaVersion?: number;
    };

class RecordError extends Error {}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) throw new RecordError(`${path} is not an object`);
  return value;
}

function str(value: unknown, path: string): string {
  if (typeof value !== 'string') throw new RecordError(`${path} is not a string`);
  return value;
}

function optionalStr(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function num(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new RecordError(`${path} is not a number`);
  }
  return value;
}

function optionalNum(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function bool(value: unknown): boolean {
  return value === true;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
  if (typeof value === 'string' && (allowed as readonly string[]).includes(value)) {
    return value as T;
  }
  throw new RecordError(`${path} is not one of ${allowed.join(', ')}`);
}

function optionalOneOf<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : null;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function strings(value: unknown): string[] {
  return list(value).filter((entry): entry is string => typeof entry === 'string');
}

function numbers(value: unknown): number[] {
  return list(value).filter(
    (entry): entry is number => typeof entry === 'number' && Number.isFinite(entry),
  );
}

function parseSitting(raw: unknown): Sitting {
  const record = requireRecord(raw, 'sitting');
  return {
    id: optionalNum(record['id']),
    date: optionalStr(record['date']),
    sourceDateTime: optionalStr(record['sourceDateTime']),
  };
}

function parseStage(raw: unknown, path: string): StageOccurrence {
  const record = requireRecord(raw, path);
  return {
    billStageId: optionalNum(record['billStageId']),
    stageId: optionalNum(record['stageId']),
    sessionId: optionalNum(record['sessionId']),
    label: optionalStr(record['label']) ?? 'Unnamed stage',
    abbreviation: optionalStr(record['abbreviation']),
    house: oneOf(record['house'], HOUSES, `${path}.house`),
    sortOrder: optionalNum(record['sortOrder']),
    sittings: list(record['sittings']).map(parseSitting),
    nextSittingDate: optionalStr(record['nextSittingDate']),
    detail: optionalStr(record['detail']),
  };
}

function parseHistoryEntry(raw: unknown, path: string): HistoryEntry {
  const record = requireRecord(raw, path);
  return {
    billStageId: optionalNum(record['billStageId']),
    stageId: optionalNum(record['stageId']),
    sessionId: optionalNum(record['sessionId']),
    label: optionalStr(record['label']) ?? 'Unnamed stage',
    abbreviation: optionalStr(record['abbreviation']),
    house: oneOf(record['house'], HOUSES, `${path}.house`),
    sortOrder: optionalNum(record['sortOrder']),
    sittings: list(record['sittings']).map(parseSitting),
    mappedNode: optionalOneOf<PipelineNode>(record['mappedNode'], PIPELINE_NODES),
    mappingMode: oneOf<MappingMode>(record['mappingMode'], MAPPING_MODES, `${path}.mappingMode`),
  };
}

function parseSponsor(raw: unknown, path: string): Sponsor {
  const record = requireRecord(raw, path);
  return {
    memberId: optionalNum(record['memberId']),
    name: str(record['name'], `${path}.name`),
    house: oneOf(record['house'], HOUSES, `${path}.house`),
    party: optionalStr(record['party']),
    organisation: optionalStr(record['organisation']),
  };
}

function parseBillType(raw: unknown): BillType | null {
  if (!isRecord(raw)) return null;
  const name = optionalStr(raw['name']);
  if (name === null) return null;
  return { id: optionalNum(raw['id']), name, category: optionalStr(raw['category']) };
}

function parseBill(raw: unknown, index: number): Bill {
  const path = `bills[${index}]`;
  const record = requireRecord(raw, path);
  return {
    id: num(record['id'], `${path}.id`),
    title: str(record['title'], `${path}.title`),
    formerTitle: optionalStr(record['formerTitle']),
    summary: optionalStr(record['summary']),
    parliamentUrl: str(record['parliamentUrl'], `${path}.parliamentUrl`),
    billType: parseBillType(record['billType']),
    originatingHouse: oneOf<House>(record['originatingHouse'], HOUSES, `${path}.originatingHouse`),
    currentHouse: oneOf<House>(record['currentHouse'], HOUSES, `${path}.currentHouse`),
    introducedSessionId: optionalNum(record['introducedSessionId']),
    includedSessionIds: numbers(record['includedSessionIds']),
    carriedOver: bool(record['carriedOver']),
    sourceLastUpdate: optionalStr(record['sourceLastUpdate']),
    withdrawnSourceDate: optionalStr(record['withdrawnSourceDate']),
    status: oneOf<BillStatus>(record['status'], BILL_STATUSES, `${path}.status`),
    pipelineNode: oneOf<PipelineNode>(
      record['pipelineNode'],
      PIPELINE_NODES,
      `${path}.pipelineNode`,
    ),
    lastKnownPipelineNode: optionalOneOf<PipelineNode>(
      record['lastKnownPipelineNode'],
      PIPELINE_NODES,
    ),
    mappingMode: oneOf<MappingMode>(record['mappingMode'], MAPPING_MODES, `${path}.mappingMode`),
    nonStandardRoute: bool(record['nonStandardRoute']),
    stage: record['stage'] == null ? null : parseStage(record['stage'], `${path}.stage`),
    sponsors: list(record['sponsors']).map((entry, i) =>
      parseSponsor(entry, `${path}.sponsors[${i}]`),
    ),
    history: list(record['history']).map((entry, i) =>
      parseHistoryEntry(entry, `${path}.history[${i}]`),
    ),
    pingPongExchangeNumber: optionalNum(record['pingPongExchangeNumber']),
    detailsComplete: bool(record['detailsComplete']),
    historyComplete: bool(record['historyComplete']),
    warnings: strings(record['warnings']),
  };
}

function parseSource(raw: unknown): SnapshotSource {
  const record = requireRecord(raw, 'source');
  return {
    name: str(record['name'], 'source.name'),
    baseUrl: str(record['baseUrl'], 'source.baseUrl'),
    sessionId: num(record['sessionId'], 'source.sessionId'),
    sessionLabel: str(record['sessionLabel'], 'source.sessionLabel'),
    attribution: str(record['attribution'], 'source.attribution'),
    licenceUrl: str(record['licenceUrl'], 'source.licenceUrl'),
  };
}

function parseCounts(raw: unknown): SnapshotCounts {
  const record = isRecord(raw) ? raw : {};
  const count = (key: string): number => optionalNum(record[key]) ?? 0;
  return {
    total: count('total'),
    active: count('active'),
    enacted: count('enacted'),
    withdrawn: count('withdrawn'),
    failed: count('failed'),
    unknown: count('unknown'),
    specialOrUnclassified: count('specialOrUnclassified'),
  };
}

function parseWarnings(raw: unknown): SnapshotWarning[] {
  return list(raw).flatMap((entry): SnapshotWarning[] => {
    if (!isRecord(entry)) return [];
    const code = optionalStr(entry['code']);
    const message = optionalStr(entry['message']);
    if (code === null || message === null) return [];
    const severity = optionalOneOf(entry['severity'], ['info', 'warning', 'error'] as const);
    return [
      {
        code,
        message,
        severity: severity ?? 'warning',
        ...(Array.isArray(entry['billIds']) ? { billIds: numbers(entry['billIds']) } : {}),
        ...(Array.isArray(entry['stageIds']) ? { stageIds: numbers(entry['stageIds']) } : {}),
      },
    ];
  });
}

/**
 * Parse a raw snapshot document.
 *
 * Never throws: every failure mode is expressed in the returned result so the
 * UI can explain what happened.
 */
export function parseSnapshot(raw: unknown): ParseResult {
  if (!isRecord(raw)) {
    return { ok: false, reason: 'malformed', message: 'The snapshot file is not a JSON object.' };
  }

  const schemaVersion = optionalNum(raw['schemaVersion']);
  if (schemaVersion === null) {
    return {
      ok: false,
      reason: 'malformed',
      message: 'The snapshot file does not declare a schemaVersion.',
    };
  }
  if (schemaVersion !== SUPPORTED_SCHEMA_VERSION) {
    return {
      ok: false,
      reason: 'unsupported-schema',
      schemaVersion,
      message:
        `This version of the site understands snapshot schema ` +
        `${SUPPORTED_SCHEMA_VERSION}, but the published data uses schema ${schemaVersion}. ` +
        `The site needs to be redeployed before it can display this data.`,
    };
  }

  const invalidRecords: InvalidRecord[] = [];
  const bills: Bill[] = [];

  for (const [index, entry] of list(raw['bills']).entries()) {
    try {
      bills.push(parseBill(entry, index));
    } catch (error) {
      // One unusable record must not remove every usable one.
      invalidRecords.push({
        index,
        id: isRecord(entry) ? optionalNum(entry['id']) : null,
        reason: error instanceof Error ? error.message : 'Unrecognised record',
      });
    }
  }

  let source: SnapshotSource;
  try {
    source = parseSource(raw['source']);
  } catch (error) {
    return {
      ok: false,
      reason: 'malformed',
      message: `The snapshot is missing its source information (${
        error instanceof Error ? error.message : 'unknown reason'
      }).`,
    };
  }

  const generatedAt = optionalStr(raw['generatedAt']);
  if (generatedAt === null) {
    return {
      ok: false,
      reason: 'malformed',
      message: 'The snapshot does not record when it was generated.',
    };
  }

  const synthetic = bool(raw['synthetic']);
  return {
    ok: true,
    invalidRecords,
    snapshot: {
      schemaVersion,
      generatedAt,
      lastFullReconciliationAt: optionalStr(raw['lastFullReconciliationAt']),
      status: synthetic ? 'synthetic' : 'healthy',
      synthetic,
      source,
      counts: parseCounts(raw['counts']),
      warnings: parseWarnings(raw['warnings']),
      dataHash: optionalStr(raw['dataHash']) ?? '',
      bills,
    },
  };
}
