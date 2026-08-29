/**
 * The published contract, checked from the frontend's side.
 *
 * The backend validates the snapshot it writes; this validates the snapshot
 * the browser reads, against the same schema file. Both halves of the
 * contract are therefore tested against one source of truth.
 */

import Ajv2020, { type ValidateFunction } from 'ajv/dist/2020';
import { describe, expect, it } from 'vitest';
import { EXAMPLE_DOCUMENT, cloneDocument, exampleSnapshot } from './helpers';
import { PIPELINE_NODES, SUPPORTED_SCHEMA_VERSION } from '../src/model/types';
// The one schema file in the repository, imported directly so this test and
// the backend contract test can never drift onto different copies.
import schemaDocument from '../../schema/snapshot.schema.json';

const schema: object = schemaDocument;

function validator(): ValidateFunction {
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  return ajv.compile(schema);
}

describe('snapshot schema', () => {
  it('accepts the checked-in example snapshot', () => {
    const validate = validator();
    const valid = validate(EXAMPLE_DOCUMENT);
    expect(validate.errors ?? []).toEqual([]);
    expect(valid).toBe(true);
  });

  it('rejects an unknown pipeline node', () => {
    const document = cloneDocument();
    (document['bills'] as Record<string, unknown>[])[0]!['pipelineNode'] = 'commons_fourth_reading';
    expect(validator()(document)).toBe(false);
  });

  it('rejects a source timestamp dressed up as UTC', () => {
    const document = cloneDocument();
    document['generatedAt'] = '2026-08-29T12:00:00';
    expect(validator()(document)).toBe(false);
  });

  it('rejects an unexpected top-level field', () => {
    const document = cloneDocument();
    document['surprise'] = true;
    expect(validator()(document)).toBe(false);
  });
});

describe('type definitions track the schema', () => {
  it('declares the same pipeline nodes as the schema', () => {
    const defs = (schema as { $defs: Record<string, { enum: string[] }> }).$defs;
    expect([...PIPELINE_NODES].sort()).toEqual([...defs['pipelineNode']!.enum].sort());
  });

  it('supports the schema version the example snapshot uses', () => {
    expect(exampleSnapshot().schemaVersion).toBe(SUPPORTED_SCHEMA_VERSION);
  });
});

describe('the example snapshot is clearly labelled', () => {
  it('is marked synthetic so the UI never presents it as live data', () => {
    const snapshot = exampleSnapshot();
    expect(snapshot.synthetic).toBe(true);
    expect(snapshot.status).toBe('synthetic');
  });

  it('carries the Open Parliament Licence attribution', () => {
    expect(exampleSnapshot().source.attribution).toBe(
      'Contains Parliamentary information licensed under the Open Parliament Licence v3.0.',
    );
  });

  it('contains no member photograph or Parliamentary image URL', () => {
    const rendered = JSON.stringify(EXAMPLE_DOCUMENT);
    expect(rendered).not.toContain('memberPhoto');
    expect(rendered).not.toContain('Thumbnail');
    expect(rendered).not.toMatch(/\.(?:jpg|jpeg|png|gif|webp)/i);
  });
});
