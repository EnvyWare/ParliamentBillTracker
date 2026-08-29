/** The rendered application: routes, filters, details and attribution. */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { NODE_INFO } from '../src/model/routes';
import { billById, exampleSnapshot, okOutcome, renderApp } from './helpers';

const snapshot = exampleSnapshot();

async function ready(): Promise<void> {
  await screen.findByRole('heading', { name: /Starts in the House of Commons/ });
}

function routePanel(name: RegExp): HTMLElement {
  const heading = screen.getByRole('heading', { name });
  const panel = heading.closest('details');
  if (panel === null) throw new Error('Route panel not found');
  return panel;
}

function bucket(routeName: RegExp, bucketName: string): HTMLElement {
  const panel = routePanel(routeName);
  const heading = within(panel).getByRole('heading', { name: new RegExp(bucketName) });
  const section = heading.closest('section');
  if (section === null) throw new Error(`Bucket ${bucketName} not found`);
  return section;
}

describe('the two routes', () => {
  it('shows both origin routes at once', async () => {
    renderApp();
    await ready();
    expect(screen.getByRole('heading', { name: /Starts in the House of Commons/ })).toBeVisible();
    expect(screen.getByRole('heading', { name: /Starts in the House of Lords/ })).toBeVisible();
  });

  it('lists the Commons route stages in legislative order', async () => {
    renderApp();
    await ready();
    const panel = routePanel(/Starts in the House of Commons/);
    const headings = within(panel)
      .getAllByRole('heading', { level: 4 })
      .map((heading) => heading.textContent ?? '');
    expect(headings).toEqual([
      '1Step 1: Commons: First Reading',
      '2Step 2: Commons: Second Reading',
      '3Step 3: Commons: Committee Stage',
      '4Step 4: Commons: Report Stage',
      '5Step 5: Commons: Third Reading',
      '6Step 6: Lords: First Reading',
      '7Step 7: Lords: Second Reading',
      '8Step 8: Lords: Committee Stage',
      '9Step 9: Lords: Report Stage',
      '10Step 10: Lords: Third Reading',
      '11Step 11: Consideration of Amendments',
      '12Step 12: Royal Assent',
    ]);
  });

  it('lists the Lords route as the mirror image', async () => {
    renderApp();
    await ready();
    const panel = routePanel(/Starts in the House of Lords/);
    const headings = within(panel)
      .getAllByRole('heading', { level: 4 })
      .map((heading) => heading.textContent ?? '');
    expect(headings[0]).toContain('Lords: First Reading');
    expect(headings[4]).toContain('Lords: Third Reading');
    expect(headings[5]).toContain('Commons: First Reading');
    expect(headings[10]).toContain('Consideration of Amendments');
    expect(headings[11]).toContain('Royal Assent');
  });

  it('describes ping-pong as an exchange with supporting text', async () => {
    renderApp();
    await ready();
    expect(NODE_INFO.ping_pong.explanation).toBe('Ping-pong: both Houses agree the final wording.');
    const section = bucket(/Starts in the House of Commons/, 'Consideration of Amendments');
    expect(within(section).getByText(/both Houses agree the final wording/)).toBeVisible();
  });

  it('shows the transfer marker between the two Houses', async () => {
    renderApp();
    await ready();
    expect(screen.getByText('Passes to the House of Lords')).toBeVisible();
    expect(screen.getByText('Passes to the House of Commons')).toBeVisible();
  });

  it('keeps empty stages visible with a zero count', async () => {
    renderApp();
    await ready();
    // Nothing is at Lords Third Reading on the Lords-first route by default.
    const section = bucket(/Starts in the House of Lords/, 'Lords: Third Reading');
    expect(within(section).getByText('0 Bills')).toBeVisible();
    expect(within(section).getByText('No Bills at this stage.')).toBeVisible();
  });

  it('shows a plain-English explanation for each stage without needing hover', async () => {
    renderApp();
    await ready();
    const section = bucket(/Starts in the House of Commons/, 'Commons: Committee Stage');
    expect(
      within(section).getByText(
        'A committee of MPs examines the Bill line by line and can amend it.',
      ),
    ).toBeVisible();
  });
});

describe('placement of Bills', () => {
  it('shows each active Bill exactly once across the whole page', async () => {
    renderApp();
    await ready();
    const active = snapshot.bills.filter(
      (bill) => bill.status === 'active' || bill.status === 'unknown',
    );
    for (const bill of active) {
      expect(screen.getAllByRole('button', { name: `${bill.title}. View details.` })).toHaveLength(
        1,
      );
    }
  });

  it('puts a Commons-origin Bill in the right bucket on the right route', async () => {
    renderApp();
    await ready();
    const section = bucket(/Starts in the House of Commons/, 'Commons: Report Stage');
    expect(within(section).getByRole('button', { name: /Health Standards Bill/ })).toBeVisible();
  });

  it('puts a Lords-origin Bill on the Lords route even once it reaches the Commons', async () => {
    renderApp();
    await ready();
    const section = bucket(/Starts in the House of Lords/, 'Commons: Second Reading');
    expect(
      within(section).getByRole('button', { name: /Charities Regulation Bill/ }),
    ).toBeVisible();
  });

  it('lists special and unclassified Bills in their own section', async () => {
    renderApp();
    await ready();
    const heading = screen.getByRole('heading', {
      name: 'Other or special Parliamentary procedure',
    });
    const section = heading.closest('section')!;
    expect(within(section).getByRole('button', { name: /Westhaven Harbour Bill/ })).toBeVisible();
    expect(within(section).getByRole('button', { name: /Example Procedure Bill/ })).toBeVisible();
    expect(within(section).getByRole('button', { name: /Unattributed Origin Bill/ })).toBeVisible();
  });

  it('marks an unrecognised stage on the card rather than hiding it', async () => {
    renderApp();
    await ready();
    const card = screen.getByRole('button', { name: /Example Procedure Bill/ });
    expect(within(card).getByText('Unrecognised stage')).toBeVisible();
  });

  it('marks a carried-over Bill following a non-standard route', async () => {
    renderApp();
    await ready();
    const card = screen.getByRole('button', { name: /Infrastructure \(Delivery\) Bill/ });
    expect(within(card).getByText('Carried over')).toBeVisible();
    expect(within(card).getByText('Non-standard route')).toBeVisible();
  });

  it('shows the ping-pong exchange number', async () => {
    renderApp();
    await ready();
    const card = screen.getByRole('button', { name: /Data Protection Bill/ });
    expect(within(card).getByText('Exchange 3')).toBeVisible();
  });

  it('hides concluded Bills by default and shows them when selected', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();
    expect(screen.queryByRole('button', { name: /Local Referendums Bill/ })).toBeNull();

    await user.selectOptions(screen.getByLabelText('Status'), 'concluded');
    expect(await screen.findByRole('heading', { name: 'No longer progressing' })).toBeVisible();
    expect(screen.getByRole('button', { name: /Local Referendums Bill/ })).toBeVisible();
    expect(screen.getByRole('button', { name: /Fixed Odds Betting Bill/ })).toBeVisible();
  });

  it('shows Acts at Royal Assent when Acts are selected', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();
    await user.selectOptions(screen.getByLabelText('Status'), 'acts');

    await waitFor(() => {
      const section = bucket(/Starts in the House of Commons/, 'Royal Assent');
      expect(within(section).getByRole('button', { name: /Finance Act 2026/ })).toBeVisible();
    });
  });
});

describe('counts', () => {
  it('reports the number of Bills shown in the header', async () => {
    renderApp();
    await ready();
    const active = snapshot.bills.filter(
      (bill) => bill.status === 'active' || bill.status === 'unknown',
    ).length;
    expect(screen.getByText(String(active))).toBeVisible();
  });

  it('makes each bucket count equal the cards it renders', async () => {
    const { container } = renderApp();
    await ready();
    const buckets = container.querySelectorAll<HTMLElement>('.bucket');
    expect(buckets.length).toBe(24); // twelve stages on each of the two routes
    for (const section of buckets) {
      const expected = Number.parseInt(
        section.querySelector('.bucket__count')?.textContent ?? '0',
        10,
      );
      const cards = within(section).queryAllByRole('button', { name: /View details\.$/ });
      expect(cards).toHaveLength(expected);
    }
  });

  it('updates counts when a filter narrows the results', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();
    await user.selectOptions(screen.getByLabelText('Status'), 'acts');

    await waitFor(() => {
      const section = bucket(/Starts in the House of Commons/, 'Commons: Report Stage');
      expect(within(section).getByText('0 Bills')).toBeVisible();
    });
  });
});

describe('filters', () => {
  it('searches across title, former title, summary and sponsor', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();
    const search = screen.getByLabelText('Search Bills');

    await user.type(search, 'National Infrastructure');
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Health Standards Bill/ })).toBeNull();
    });
    // Matched on its former title rather than its current one.
    expect(screen.getByRole('button', { name: /Infrastructure \(Delivery\) Bill/ })).toBeVisible();

    await user.clear(search);
    await user.type(search, 'Wesley Marchant');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Health Standards Bill/ })).toBeVisible();
    });
  });

  it('combines filters and shows removable chips', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /more filters/ }));
    await user.selectOptions(screen.getByLabelText('Starts in'), 'lords');
    await user.selectOptions(screen.getByLabelText('Currently in'), 'lords');

    // The accessible name joins the visible label and the visually hidden
    // suffix with a space, so these match on the label alone.
    const originChip = await screen.findByRole('button', { name: /Starts in: House of Lords/ });
    expect(originChip).toBeVisible();
    expect(originChip).toHaveAccessibleName('Starts in: House of Lords , remove this filter');
    expect(screen.getByRole('button', { name: /Currently in: House of Lords/ })).toBeVisible();

    await user.click(originChip);
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Starts in: House of Lords/ })).toBeNull();
    });
    // Removing one chip leaves the other in place.
    expect(screen.getByRole('button', { name: /Currently in: House of Lords/ })).toBeVisible();
  });

  it('clears everything with Clear all', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.selectOptions(screen.getByLabelText('Status'), 'all');
    await user.click(await screen.findByRole('button', { name: 'Clear all' }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Clear all' })).toBeNull();
    });
    expect(window.location.search).toBe('');
  });

  it('keeps the full pipeline visible when nothing matches', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.type(screen.getByLabelText('Search Bills'), 'zzzzzzzz');
    expect(
      await screen.findByRole('heading', { name: 'No Bills match these filters' }),
    ).toBeVisible();

    // The process itself is still explained, with every stage at zero.
    expect(screen.getByRole('heading', { name: /Starts in the House of Commons/ })).toBeVisible();
    const section = bucket(/Starts in the House of Commons/, 'Commons: Report Stage');
    expect(within(section).getByText('0 Bills')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Reset filters' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Health Standards Bill/ })).toBeVisible();
    });
  });

  it('announces the result count through one polite live region', async () => {
    renderApp();
    await ready();
    const regions = screen.getAllByRole('status');
    expect(regions).toHaveLength(1);
    expect(regions[0]).toHaveTextContent(/\d+ Bills match the current filters\./);
  });
});

describe('the address bar', () => {
  it('records filters so a copied link reproduces the view', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.selectOptions(screen.getByLabelText('Status'), 'acts');
    await waitFor(() => {
      expect(window.location.search).toBe('?status=acts');
    });
  });

  it('restores a view from the query string on load', async () => {
    renderApp({ search: '?status=concluded' });
    await ready();
    expect(await screen.findByRole('heading', { name: 'No longer progressing' })).toBeVisible();
    expect(screen.getByLabelText('Status')).toHaveValue('concluded');
  });

  it('opens the right Bill from a direct ?bill= link', async () => {
    renderApp({ search: '?bill=9004' });
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Health Standards Bill' })).toBeVisible();
  });

  it('opens a Bill excluded by the current filters from a direct link', async () => {
    // The default status filter hides Acts, but a shared link must still work.
    renderApp({ search: '?bill=9021' });
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Finance Act 2026' })).toBeVisible();
  });
});

describe('the details panel', () => {
  it('opens from a card and shows the Bill', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Health Standards Bill/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Health Standards Bill' })).toBeVisible();
    expect(window.location.search).toBe('?bill=9004');
  });

  it('has an accessible name and takes focus', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Health Standards Bill/ }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAccessibleName('Health Standards Bill');
    expect(within(dialog).getByRole('button', { name: 'Close Bill details' })).toHaveFocus();
  });

  it('shows the official stage wording alongside the normalised stage', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Infrastructure \(Delivery\) Bill/ }));
    const dialog = await screen.findByRole('dialog');
    const summary = within(dialog).getByRole('heading', { name: 'Where it is now' }).parentElement!;
    expect(within(summary).getByText('Commons: Committee Stage')).toBeVisible();
    // The raw label is kept alongside the normalised stage. It appears again
    // further down in the stage history, which is why this is scoped.
    expect(within(summary).getByText('Carry-over motion')).toBeVisible();
  });

  it('lists sponsors by name with no image', async () => {
    const user = userEvent.setup();
    const { container } = renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Health Standards Bill/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Wesley Marchant/)).toBeVisible();
    expect(container.querySelectorAll('img')).toHaveLength(0);
  });

  it('shows the stage history in order', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Data Protection Bill/ }));
    const dialog = await screen.findByRole('dialog');
    const items = [...dialog.querySelectorAll('.timeline__item')].map(
      (item) => item.textContent ?? '',
    );
    expect(items).toHaveLength(13);
    expect(items[0]).toContain('1st reading');
    expect(items[12]).toContain('Consideration of Lords message');
    expect(within(dialog).getByText(/Exchange 3/)).toBeVisible();
  });

  it('offers a prominent link to the Bill on the Parliament website', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Health Standards Bill/ }));
    const dialog = await screen.findByRole('dialog');
    const link = within(dialog).getByRole('link', { name: /View on UK Parliament/ });
    expect(link).toHaveAttribute('href', billById(9004).parliamentUrl);
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('explains a warning in full', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Example Procedure Bill/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/does not yet recognise/)).toBeVisible();
  });

  it('closes with the close button and restores focus to the card', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    const card = screen.getByRole('button', { name: /Health Standards Bill/ });
    await user.click(card);
    const dialog = await screen.findByRole('dialog');

    await user.click(within(dialog).getByRole('button', { name: 'Close Bill details' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Health Standards Bill/ })).toHaveFocus();
    });
  });

  it('closes with Escape', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Health Standards Bill/ }));
    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  it('closes when the browser goes back, and restores focus', async () => {
    const user = userEvent.setup();
    renderApp();
    await ready();

    await user.click(screen.getByRole('button', { name: /Health Standards Bill/ }));
    await screen.findByRole('dialog');
    expect(window.location.search).toBe('?bill=9004');

    window.history.back();
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Health Standards Bill/ })).toHaveFocus();
    });
  });

  it('makes no further network request when opening a Bill', async () => {
    const user = userEvent.setup();
    let loads = 0;
    renderApp({
      load: () => {
        loads += 1;
        return Promise.resolve(okOutcome());
      },
    });
    await ready();
    expect(loads).toBe(1);

    await user.click(screen.getByRole('button', { name: /Health Standards Bill/ }));
    await screen.findByRole('dialog');
    expect(loads).toBe(1);
  });
});

describe('attribution', () => {
  it('shows the exact Open Parliament Licence sentence, linked', async () => {
    renderApp();
    await ready();
    const footer = screen.getByRole('contentinfo');
    expect(
      within(footer).getByText(/Contains Parliamentary information licensed under the/),
    ).toBeVisible();
    const link = within(footer).getByRole('link', { name: 'Open Parliament Licence v3.0' });
    expect(link).toHaveAttribute(
      'href',
      'https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/',
    );
  });

  it('shows the unofficial disclaimer', async () => {
    renderApp();
    await ready();
    expect(
      within(screen.getByRole('contentinfo')).getByText(
        'This is an independent, unofficial project and is not affiliated with or endorsed by UK Parliament.',
      ),
    ).toBeVisible();
  });

  it('shows the unofficial badge beside the product name', async () => {
    renderApp();
    await ready();
    const banner = screen.getByRole('banner');
    expect(within(banner).getByText('UK Bill Pipeline')).toBeVisible();
    expect(within(banner).getByText('Unofficial project')).toBeVisible();
  });

  it('links to the source repository', async () => {
    renderApp();
    await ready();
    expect(
      within(screen.getByRole('contentinfo')).getByRole('link', { name: /repository on GitHub/ }),
    ).toBeVisible();
  });
});
