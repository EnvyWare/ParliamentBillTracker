/** Loading, healthy, stale, cached, synthetic, unsupported and failed states. */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { LoadOutcome } from '../src/model/load';
import { TEST_NOW, cloneDocument, okOutcome, renderApp } from './helpers';

function liveDocument(generatedAt: string): Record<string, unknown> {
  const document = cloneDocument();
  document['synthetic'] = false;
  document['status'] = 'healthy';
  document['generatedAt'] = generatedAt;
  // Run warnings are exercised separately; these tests are about freshness.
  document['warnings'] = [];
  return document;
}

const never = (): Promise<LoadOutcome> => new Promise<LoadOutcome>(() => undefined);

describe('loading', () => {
  it('shows a pipeline-shaped skeleton while the data is on its way', () => {
    const { container } = renderApp({ load: never });
    expect(screen.getByText('Loading Bill data.')).toBeInTheDocument();
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(10);
    // The skeleton mirrors the real layout so the page does not jump.
    expect(container.querySelectorAll('.bucket')).toHaveLength(24);
  });
});

describe('healthy data', () => {
  it('shows no warning banner for a fresh live snapshot', async () => {
    const { container } = renderApp({ document: liveDocument('2026-08-29T12:30:00Z') });
    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
    expect(container.querySelectorAll('.banner')).toHaveLength(0);
  });

  it('shows the retrieval time in relative and absolute UK time', async () => {
    renderApp({ document: liveDocument('2026-08-29T12:48:00Z') });
    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
    const banner = screen.getByRole('banner');
    expect(within(banner).getByText(/Retrieved 12 minutes ago/)).toBeVisible();
    expect(within(banner).getByText('29 August 2026, 13:48 BST')).toBeVisible();
  });
});

describe('synthetic data', () => {
  it('is labelled as example data', async () => {
    renderApp();
    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
    expect(screen.getByText('Example data')).toBeVisible();
    expect(screen.getByText(/do not describe any real Bill/)).toBeVisible();
  });

  it('is never reported as stale, however old its fixed timestamp is', async () => {
    renderApp({ now: new Date('2030-01-01T00:00:00Z') });
    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
    expect(screen.queryByText('Data may be out of date')).toBeNull();
  });
});

describe('stale data', () => {
  it('warns without hiding the Bills', async () => {
    renderApp({ document: liveDocument('2026-08-29T08:00:00Z') });
    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
    expect(screen.getByText('Data may be out of date')).toBeVisible();
    // The warning is non-blocking: the data is still there.
    expect(screen.getByRole('button', { name: /Health Standards Bill/ })).toBeVisible();
  });

  it('does not warn inside the three-hour threshold', async () => {
    renderApp({ document: liveDocument('2026-08-29T10:30:00Z') });
    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
    expect(screen.queryByText('Data may be out of date')).toBeNull();
  });
});

describe('cached data', () => {
  it('falls back to the cache when the network fails, and says so', async () => {
    renderApp({
      load: () =>
        Promise.resolve({
          kind: 'error',
          reason: 'network',
          message: 'The data file could not be loaded. You may be offline.',
        }),
      readCache: () => okOutcome(liveDocument('2026-08-29T09:00:00Z'), 'cache'),
    });

    expect(await screen.findByText('Cached data')).toBeVisible();
    expect(screen.getByText(/copy your browser saved/)).toBeVisible();
    expect(screen.getByRole('button', { name: /Health Standards Bill/ })).toBeVisible();
  });

  it('does not use the cache to paper over a malformed live file', async () => {
    // Showing older data without explaining why would be worse than the error.
    renderApp({
      load: () =>
        Promise.resolve({
          kind: 'error',
          reason: 'malformed',
          message: 'The snapshot file is not a JSON object.',
        }),
      readCache: () => okOutcome(),
    });

    expect(
      await screen.findByRole('heading', { name: 'Bill data could not be loaded' }),
    ).toBeVisible();
  });
});

describe('failure', () => {
  it('shows a full-page error and a Retry button when nothing can be shown', async () => {
    renderApp({
      load: () =>
        Promise.resolve({
          kind: 'error',
          reason: 'network',
          message: 'The data file could not be loaded. You may be offline.',
        }),
    });

    const alert = await screen.findByRole('alert');
    expect(
      within(alert).getByRole('heading', { name: 'Bill data could not be loaded' }),
    ).toBeVisible();
    expect(within(alert).getByText(/You may be offline/)).toBeVisible();
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeVisible();
  });

  it('reloads when Retry is pressed', async () => {
    const user = userEvent.setup();
    const load = vi
      .fn<() => Promise<LoadOutcome>>()
      .mockResolvedValueOnce({
        kind: 'error',
        reason: 'network',
        message: 'The data file could not be loaded. You may be offline.',
      })
      .mockResolvedValue(okOutcome());

    renderApp({ load });
    await user.click(await screen.findByRole('button', { name: 'Retry' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Starts in the House of Commons/ })).toBeVisible();
    });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('still shows the licence attribution and disclaimer when the data fails', async () => {
    renderApp({
      load: () => Promise.resolve({ kind: 'error', reason: 'network', message: 'Offline.' }),
    });
    await screen.findByRole('alert');

    const footer = screen.getByRole('contentinfo');
    expect(
      within(footer).getByText(/Contains Parliamentary information licensed under the/),
    ).toBeVisible();
    expect(
      within(footer).getByText(
        'This is an independent, unofficial project and is not affiliated with or endorsed by UK Parliament.',
      ),
    ).toBeVisible();
    expect(screen.getByText('Unofficial project')).toBeVisible();
  });
});

describe('an unsupported schema version', () => {
  it('explains the problem rather than behaving unpredictably', async () => {
    const document = cloneDocument();
    document['schemaVersion'] = 99;
    renderApp({ document });

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(/schema 99/)).toBeVisible();
    expect(within(alert).getByText(/needs to be redeployed/)).toBeVisible();
  });

  it('offers no Retry, because retrying cannot help', async () => {
    const document = cloneDocument();
    document['schemaVersion'] = 99;
    renderApp({ document });

    await screen.findByRole('alert');
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  });
});

describe('individual bad records', () => {
  it('isolates one unreadable Bill and renders the rest', async () => {
    const document = cloneDocument();
    const bills = document['bills'] as Record<string, unknown>[];
    bills[0] = { id: 1, title: 42 };
    renderApp({ document });

    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
    expect(screen.getByText('1 record could not be read')).toBeVisible();
    expect(screen.getByRole('button', { name: /Health Standards Bill/ })).toBeVisible();
  });
});

describe('run warnings from the pipeline', () => {
  it('surfaces an unrecognised stage warning to the reader', async () => {
    renderApp();
    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
    expect(screen.getByText(/does not recognise and are shown as unclassified/)).toBeVisible();
  });
});

describe('the browser never contacts Parliament', () => {
  it('requests only the same-origin snapshot file', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(cloneDocument()), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    const { fetchSnapshot } = await import('../src/model/load');
    const outcome = await fetchSnapshot({ fetchImpl, now: () => TEST_NOW });

    expect(outcome.kind).toBe('ok');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(typeof url).toBe('string');
    expect(url).toBe('/data/current.json');
    expect(url as string).not.toContain('parliament.uk');
    expect(init).toMatchObject({ cache: 'no-cache' });
  });
});
