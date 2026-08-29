import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { serveSnapshot } from './fixtures';

/** No serious or critical issue is permitted in any state. */
async function auditSeriousIssues(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();

  return results.violations
    .filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
    .map(
      (violation) =>
        `${violation.id} (${violation.impact ?? 'unknown'}): ${violation.help} — ` +
        violation.nodes
          .slice(0, 3)
          .map((node) => node.target.join(' '))
          .join('; '),
    );
}

test.describe('accessibility', () => {
  test('the main view has no serious or critical issues', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();
    expect(await auditSeriousIssues(page)).toEqual([]);
  });

  test('the mobile view has no serious or critical issues', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();
    expect(await auditSeriousIssues(page)).toEqual([]);
  });

  test('the empty result state has no serious or critical issues', async ({ page }) => {
    await page.goto('/?q=zzzzzzzzzz');
    await expect(page.getByRole('heading', { name: 'No Bills match these filters' })).toBeVisible();
    expect(await auditSeriousIssues(page)).toEqual([]);
  });

  test('the details sheet has no serious or critical issues', async ({ page }) => {
    await page.goto('/?bill=9004');
    await expect(page.getByRole('dialog')).toBeVisible();
    expect(await auditSeriousIssues(page)).toEqual([]);
  });

  test('the stale-data state has no serious or critical issues', async ({ page }) => {
    await serveSnapshot(page, (document) => {
      document['synthetic'] = false;
      document['status'] = 'healthy';
      document['generatedAt'] = '2020-01-01T00:00:00Z';
    });
    await page.goto('/');
    await expect(page.getByText('Data may be out of date')).toBeVisible();
    expect(await auditSeriousIssues(page)).toEqual([]);
  });

  test('the failed state has no serious or critical issues', async ({ page }) => {
    await page.route('**/data/current.json', async (route) => {
      await route.fulfill({ status: 503, contentType: 'text/plain', body: 'unavailable' });
    });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: 'Bill data could not be loaded' }),
    ).toBeVisible();
    expect(await auditSeriousIssues(page)).toEqual([]);
  });

  test('does not rely on colour alone for House, status or warnings', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');

    // The House a Bill sits in is named in text on its route heading, and
    // every warning chip carries a word, not just a colour.
    await expect(
      page.getByRole('heading', { name: 'First House: House of Commons' }),
    ).toBeVisible();
    await expect(page.getByText('Non-standard route').first()).toBeVisible();
    await expect(page.getByText('Carried over').first()).toBeVisible();
  });

  test('hides decorative connectors from assistive technology', async ({ page }) => {
    await page.goto('/');
    const exposedRules = await page.evaluate(
      () => document.querySelectorAll('.transfer__rule:not([aria-hidden="true"])').length,
    );
    expect(exposedRules).toBe(0);
  });

  // The mark is deliberately NOT in the rule above. It used to be a decorative
  // bar, but it is now the EnvyWare logo, and it carries the only mention of
  // who publishes this in the heading. Hiding it would drop that name.
  test('exposes the brand mark by name rather than hiding it', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('img', { name: 'EnvyWare' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toHaveAccessibleName(
      'EnvyWare UK Bill Pipeline',
    );
  });

  test('announces result counts through a single polite live region', async ({ page }) => {
    await page.goto('/');
    const politeRegions = page.locator('[aria-live="polite"]:not([aria-busy])');
    await expect(politeRegions).toHaveCount(1);
  });

  test('gives the details sheet an accessible name and a modal role', async ({ page }) => {
    await page.goto('/?bill=9004');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
    await expect(dialog).toHaveAccessibleName('Health Standards Bill');
  });
});

test.describe('the Bill journey page', () => {
  test('has no serious or critical issues', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/?bill=9011&view=journey');
    await expect(
      page.getByRole('heading', { level: 2, name: 'Data Protection Bill' }),
    ).toBeVisible();
    expect(await auditSeriousIssues(page)).toEqual([]);
  });

  test('has no serious or critical issues on a narrow screen', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/?bill=9011&view=journey');
    await expect(
      page.getByRole('heading', { level: 2, name: 'Data Protection Bill' }),
    ).toBeVisible();
    expect(await auditSeriousIssues(page)).toEqual([]);
  });

  test('publishes the diagram as an image with a text alternative', async ({ page }) => {
    await page.goto('/?bill=9011&view=journey');

    // The picture is announced as one image with a summary, rather than as a
    // pile of unlabelled shapes.
    const diagram = page.getByRole('img', { name: /How Data Protection Bill moves through/ });
    await expect(diagram).toBeVisible();
    await expect(diagram).toHaveAccessibleDescription(/10 of 12 stages completed/);

    // The same route is published as real text, so the diagram is never the
    // only way to get the information.
    await expect(page.locator('.flow-scroll ol li').first()).toContainText('Step 1');
  });

  test('keeps a single h1 on the Bill page', async ({ page }) => {
    await page.goto('/?bill=9011&view=journey');
    await expect(page.locator('h1')).toHaveCount(1);
  });
});
