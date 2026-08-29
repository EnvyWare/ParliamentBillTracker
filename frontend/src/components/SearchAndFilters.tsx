import { useId, useMemo, useState } from 'react';
import { NODE_INFO, ROUTE_STEP_NODES } from '../model/routes';
import { HOUSES, type House, type PipelineNode, type Snapshot } from '../model/types';
import {
  activeFilterCount,
  billTypeOptions,
  isDefaultFilters,
  stageOptions,
  STATUS_FILTERS,
  STATUS_FILTER_LABELS,
  type FilterState,
  type StatusFilter,
} from '../selectors/filters';

const HOUSE_LABEL: Record<House, string> = {
  commons: 'House of Commons',
  lords: 'House of Lords',
  unassigned: 'Not stated',
};

interface SearchAndFiltersProps {
  readonly snapshot: Snapshot;
  readonly filters: FilterState;
  readonly searchInput: string;
  readonly onSearchChange: (value: string) => void;
  readonly onFiltersChange: (filters: FilterState) => void;
  readonly onClear: () => void;
}

interface ActiveChip {
  readonly key: string;
  readonly label: string;
  readonly clear: () => void;
}

export function SearchAndFilters({
  snapshot,
  filters,
  searchInput,
  onSearchChange,
  onFiltersChange,
  onClear,
}: SearchAndFiltersProps): React.JSX.Element {
  const ids = useId();
  const [secondaryOpen, setSecondaryOpen] = useState(false);

  const types = useMemo(() => billTypeOptions(snapshot), [snapshot]);
  const stages = useMemo(() => {
    const present = new Set(stageOptions(snapshot));
    const ordered = ROUTE_STEP_NODES.filter((node) => present.has(node));
    const extras = [...present].filter((node) => !ordered.includes(node));
    return [...ordered, ...extras];
  }, [snapshot]);

  const update = (patch: Partial<FilterState>): void => {
    onFiltersChange({ ...filters, ...patch });
  };

  const chips: ActiveChip[] = [];
  if (filters.status !== 'in_progress') {
    chips.push({
      key: 'status',
      label: `Status: ${STATUS_FILTER_LABELS[filters.status]}`,
      clear: () => {
        update({ status: 'in_progress' });
      },
    });
  }
  if (filters.originatingHouse !== null) {
    chips.push({
      key: 'origin',
      label: `Starts in: ${HOUSE_LABEL[filters.originatingHouse]}`,
      clear: () => {
        update({ originatingHouse: null });
      },
    });
  }
  if (filters.currentHouse !== null) {
    chips.push({
      key: 'house',
      label: `Currently in: ${HOUSE_LABEL[filters.currentHouse]}`,
      clear: () => {
        update({ currentHouse: null });
      },
    });
  }
  if (filters.stage !== null) {
    chips.push({
      key: 'stage',
      label: `Stage: ${NODE_INFO[filters.stage].label}`,
      clear: () => {
        update({ stage: null });
      },
    });
  }
  if (filters.billType !== null) {
    chips.push({
      key: 'type',
      label: `Type: ${filters.billType}`,
      clear: () => {
        update({ billType: null });
      },
    });
  }

  const secondaryCount = activeFilterCount({ ...filters, search: '', status: 'in_progress' });

  return (
    <section className="shell" aria-labelledby={`${ids}-filters-heading`}>
      <div className="filters">
        <h2 className="visually-hidden" id={`${ids}-filters-heading`}>
          Search and filter Bills
        </h2>

        <div className="filters__primary">
          <div className="field field--grow">
            <label className="field__label" htmlFor={`${ids}-search`}>
              Search Bills
            </label>
            <input
              id={`${ids}-search`}
              type="search"
              value={searchInput}
              placeholder="Title, former title, summary or sponsor"
              onChange={(event) => {
                onSearchChange(event.target.value);
              }}
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor={`${ids}-status`}>
              Status
            </label>
            <select
              id={`${ids}-status`}
              value={filters.status}
              onChange={(event) => {
                update({ status: event.target.value as StatusFilter });
              }}
            >
              {STATUS_FILTERS.map((status) => (
                <option key={status} value={status}>
                  {STATUS_FILTER_LABELS[status]}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="button"
          className="button button--quiet filters__disclosure"
          aria-expanded={secondaryOpen}
          aria-controls={`${ids}-secondary`}
          onClick={() => {
            setSecondaryOpen((value) => !value);
          }}
        >
          {secondaryOpen ? 'Hide' : 'Show'} more filters
          {secondaryCount > 0 && ` (${secondaryCount} active)`}
        </button>

        <div className="filters__secondary" id={`${ids}-secondary`} hidden={!secondaryOpen}>
          <div className="field">
            <label className="field__label" htmlFor={`${ids}-origin`}>
              Starts in
            </label>
            <select
              id={`${ids}-origin`}
              value={filters.originatingHouse ?? ''}
              onChange={(event) => {
                update({ originatingHouse: (event.target.value || null) as House | null });
              }}
            >
              <option value="">Either House</option>
              {HOUSES.map((house) => (
                <option key={house} value={house}>
                  {HOUSE_LABEL[house]}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor={`${ids}-house`}>
              Currently in
            </label>
            <select
              id={`${ids}-house`}
              value={filters.currentHouse ?? ''}
              onChange={(event) => {
                update({ currentHouse: (event.target.value || null) as House | null });
              }}
            >
              <option value="">Either House</option>
              {HOUSES.map((house) => (
                <option key={house} value={house}>
                  {HOUSE_LABEL[house]}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor={`${ids}-stage`}>
              Current stage
            </label>
            <select
              id={`${ids}-stage`}
              value={filters.stage ?? ''}
              onChange={(event) => {
                update({ stage: (event.target.value || null) as PipelineNode | null });
              }}
            >
              <option value="">Any stage</option>
              {stages.map((node) => (
                <option key={node} value={node}>
                  {NODE_INFO[node].label}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor={`${ids}-type`}>
              Bill type
            </label>
            <select
              id={`${ids}-type`}
              value={filters.billType ?? ''}
              onChange={(event) => {
                update({ billType: event.target.value || null });
              }}
            >
              <option value="">Any type</option>
              {types.map((type) => (
                <option key={type.name} value={type.name}>
                  {type.category === null ? type.name : `${type.category} — ${type.name}`}
                </option>
              ))}
            </select>
          </div>
        </div>

        {(chips.length > 0 || !isDefaultFilters(filters)) && (
          <div className="chips">
            <span className="chips__label">Active filters:</span>
            {filters.search.trim() !== '' && (
              <button
                type="button"
                className="chip-remove"
                onClick={() => {
                  onSearchChange('');
                }}
              >
                Search: “{filters.search}”
                <span className="visually-hidden">, remove this filter</span>
              </button>
            )}
            {chips.map((chip) => (
              <button type="button" className="chip-remove" key={chip.key} onClick={chip.clear}>
                {chip.label}
                <span className="visually-hidden">, remove this filter</span>
              </button>
            ))}
            <button type="button" className="button button--quiet" onClick={onClear}>
              Clear all
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
