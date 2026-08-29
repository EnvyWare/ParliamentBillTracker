/**
 * TypeScript half of the published contract in `schema/snapshot.schema.json`.
 *
 * Parliamentary information described by these types is licensed under the
 * Open Parliament Licence v3.0 and is not covered by this repository's MIT
 * licence. See THIRD_PARTY_NOTICES.md.
 */

export const SUPPORTED_SCHEMA_VERSION = 1;

export const HOUSES = ['commons', 'lords', 'unassigned'] as const;
export type House = (typeof HOUSES)[number];

export const BILL_STATUSES = ['active', 'enacted', 'withdrawn', 'failed', 'unknown'] as const;
export type BillStatus = (typeof BILL_STATUSES)[number];

export const PIPELINE_NODES = [
  'commons_first_reading',
  'commons_second_reading',
  'commons_committee',
  'commons_report',
  'commons_third_reading',
  'lords_first_reading',
  'lords_second_reading',
  'lords_committee',
  'lords_report',
  'lords_third_reading',
  'ping_pong',
  'royal_assent',
  'special_procedure',
  'withdrawn',
  'failed',
  'unknown',
] as const;
export type PipelineNode = (typeof PIPELINE_NODES)[number];

export const MAPPING_MODES = [
  'direct',
  'previous_canonical',
  'terminal',
  'special',
  'unknown',
] as const;
export type MappingMode = (typeof MAPPING_MODES)[number];

/** Nodes that appear as a step on one of the two canonical routes. */
export const ROUTE_NODES = [
  'commons_first_reading',
  'commons_second_reading',
  'commons_committee',
  'commons_report',
  'commons_third_reading',
  'lords_first_reading',
  'lords_second_reading',
  'lords_committee',
  'lords_report',
  'lords_third_reading',
  'ping_pong',
  'royal_assent',
] as const;

export const TERMINAL_STATUSES = ['enacted', 'withdrawn', 'failed'] as const;
export type TerminalStatus = (typeof TERMINAL_STATUSES)[number];

export interface Sitting {
  readonly id: number | null;
  /** Parliamentary calendar date. Not an instant, and it carries no offset. */
  readonly date: string | null;
  /** Verbatim source value, retained without an invented offset. */
  readonly sourceDateTime: string | null;
}

export interface StageOccurrence {
  readonly billStageId: number | null;
  readonly stageId: number | null;
  readonly sessionId: number | null;
  readonly label: string;
  readonly abbreviation: string | null;
  readonly house: House;
  readonly sortOrder: number | null;
  readonly sittings: readonly Sitting[];
  readonly nextSittingDate: string | null;
  /** The real stage label when the normalised node differs from it. */
  readonly detail: string | null;
}

export interface HistoryEntry {
  readonly billStageId: number | null;
  readonly stageId: number | null;
  readonly sessionId: number | null;
  readonly label: string;
  readonly abbreviation: string | null;
  readonly house: House;
  readonly sortOrder: number | null;
  readonly sittings: readonly Sitting[];
  readonly mappedNode: PipelineNode | null;
  readonly mappingMode: MappingMode;
}

export interface Sponsor {
  readonly memberId: number | null;
  readonly name: string;
  readonly house: House;
  readonly party: string | null;
  readonly organisation: string | null;
}

export interface BillType {
  readonly id: number | null;
  readonly name: string;
  readonly category: string | null;
}

export interface Bill {
  readonly id: number;
  readonly title: string;
  readonly formerTitle: string | null;
  readonly summary: string | null;
  readonly parliamentUrl: string;
  readonly billType: BillType | null;
  readonly originatingHouse: House;
  readonly currentHouse: House;
  readonly introducedSessionId: number | null;
  readonly includedSessionIds: readonly number[];
  readonly carriedOver: boolean;
  readonly sourceLastUpdate: string | null;
  readonly withdrawnSourceDate: string | null;
  readonly status: BillStatus;
  readonly pipelineNode: PipelineNode;
  readonly lastKnownPipelineNode: PipelineNode | null;
  readonly mappingMode: MappingMode;
  readonly nonStandardRoute: boolean;
  readonly stage: StageOccurrence | null;
  readonly sponsors: readonly Sponsor[];
  readonly history: readonly HistoryEntry[];
  readonly pingPongExchangeNumber: number | null;
  readonly detailsComplete: boolean;
  readonly historyComplete: boolean;
  readonly warnings: readonly string[];
}

export interface SnapshotSource {
  readonly name: string;
  readonly baseUrl: string;
  readonly sessionId: number;
  readonly sessionLabel: string;
  readonly attribution: string;
  readonly licenceUrl: string;
}

export interface SnapshotCounts {
  readonly total: number;
  readonly active: number;
  readonly enacted: number;
  readonly withdrawn: number;
  readonly failed: number;
  readonly unknown: number;
  readonly specialOrUnclassified: number;
}

export interface SnapshotWarning {
  readonly code: string;
  readonly message: string;
  readonly severity: 'info' | 'warning' | 'error';
  readonly billIds?: readonly number[];
  readonly stageIds?: readonly number[];
}

export interface Snapshot {
  readonly schemaVersion: number;
  readonly generatedAt: string;
  readonly lastFullReconciliationAt: string | null;
  readonly status: 'healthy' | 'synthetic';
  readonly synthetic: boolean;
  readonly source: SnapshotSource;
  readonly counts: SnapshotCounts;
  readonly warnings: readonly SnapshotWarning[];
  readonly dataHash: string;
  readonly bills: readonly Bill[];
}

/** A Bill record that could not be understood and was set aside. */
export interface InvalidRecord {
  readonly index: number;
  readonly id: number | null;
  readonly reason: string;
}
