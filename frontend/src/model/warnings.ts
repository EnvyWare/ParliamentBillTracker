/**
 * Human-readable text for the machine-readable warning codes in the snapshot.
 *
 * Warnings are shown, not hidden: a Bill this site could not place confidently
 * should say so on its own card rather than look like every other record.
 */

export interface WarningText {
  /** Short chip label. */
  readonly label: string;
  /** Sentence shown in the details panel. */
  readonly description: string;
  /** Whether the warning is worth a chip on the compact card. */
  readonly showOnCard: boolean;
}

export const WARNING_TEXT: Record<string, WarningText> = {
  terminal_flags_conflict: {
    label: 'Conflicting status',
    description:
      'The source data reported more than one final outcome for this Bill. The status shown follows a fixed order of precedence: withdrawn, then defeated, then enacted.',
    showOnCard: true,
  },
  unknown_stage_id: {
    label: 'Unrecognised stage',
    description:
      'This Bill is at a stage this site does not yet recognise, so it has not been placed on the standard route. The official stage name is shown above.',
    showOnCard: true,
  },
  no_current_stage: {
    label: 'No current stage',
    description: 'The source data does not report a current stage for this Bill.',
    showOnCard: true,
  },
  no_canonical_predecessor: {
    label: 'Special procedure',
    description:
      'This Bill is at a procedural stage with no earlier main stage to place it against, so it is shown under special procedure.',
    showOnCard: false,
  },
  unassigned_originating_house: {
    label: 'Origin not stated',
    description:
      'The source data does not say which House this Bill started in, so it cannot be placed on either route.',
    showOnCard: true,
  },
  incomplete_history: {
    label: 'Partial history',
    description:
      'The full stage history for this Bill was not available when the data was collected.',
    showOnCard: true,
  },
  incomplete_details: {
    label: 'Partial details',
    description: 'Full details for this Bill were not available when the data was collected.',
    showOnCard: true,
  },
  non_standard_route: {
    label: 'Non-standard route',
    description:
      'This Bill is at a procedural stage that runs alongside the main process, such as a carry-over or programme motion. It is shown at the last main stage it reached.',
    showOnCard: true,
  },
};

export function warningText(code: string): WarningText {
  return (
    WARNING_TEXT[code] ?? {
      label: code.replace(/_/g, ' '),
      description: `The data included a warning code this site does not recognise: ${code}.`,
      showOnCard: false,
    }
  );
}

/** Codes worth showing as a chip on the compact Bill card. */
export function cardWarnings(codes: readonly string[]): readonly string[] {
  return codes.filter((code) => warningText(code).showOnCard);
}
