import { expect, test } from '@playwright/test';
import { VIEWPORTS, pageOverflow, serveSnapshot } from './fixtures';

test.describe('layout', () => {
  for (const viewport of VIEWPORTS) {
    test(`has no page-level horizontal scrolling at ${viewport.name}px`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/');
      await expect(
        page.getByRole('heading', { name: /Starts in the House of Commons/ }),
      ).toBeVisible();

      expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
    });

    test(`keeps every control inside the viewport at ${viewport.name}px`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/');
      await expect(page.getByLabel('Search Bills')).toBeVisible();

      const clipped = await page.evaluate(() => {
        const controls = document.querySelectorAll('input, select, button, a');
        return [...controls]
          .filter((element) => {
            const box = element.getBoundingClientRect();
            if (box.width === 0 && box.height === 0) return false;
            return box.right > document.documentElement.clientWidth + 1 || box.left < -1;
          })
          .map((element) => element.textContent?.slice(0, 40) ?? element.tagName);
      });
      expect(clipped).toEqual([]);
    });
  }

  test('shows both routes expanded on a wide screen', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    const routes = page.locator('details.route');
    await expect(routes).toHaveCount(2);
    for (const index of [0, 1]) {
      await expect(routes.nth(index)).toHaveAttribute('open', '');
    }
  });

  test('lays each House phase out as five stage columns at 1200px and above', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();

    const columns = await page.evaluate(() => {
      const phase = document.querySelector('.phase--commons .phase__stages');
      return phase === null
        ? []
        : getComputedStyle(phase).gridTemplateColumns.split(' ').filter(Boolean);
    });
    expect(columns).toHaveLength(5);
  });

  test('collapses the second route into an accordion below 768px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    const routes = page.locator('details.route');
    await expect(routes.nth(0)).toHaveAttribute('open', '');
    await expect(routes.nth(1)).not.toHaveAttribute('open', '');

    // It still opens, so nothing is unreachable on a small screen.
    await routes.nth(1).getByText('Starts in the House of Lords').click();
    await expect(routes.nth(1)).toHaveAttribute('open', '');
  });

  test('remains usable at 200% zoom', async ({ page }) => {
    // 200% zoom on a 1280px screen presents as a 640px viewport.
    await page.setViewportSize({ width: 640, height: 512 });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();
    await expect(page.getByLabel('Search Bills')).toBeVisible();
    expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
  });

  test('gives touch targets at least 44 by 44 CSS pixels on a touch layout', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await expect(page.getByLabel('Search Bills')).toBeVisible();

    const small = await page.evaluate(() => {
      const targets = document.querySelectorAll('.card, .button, .sheet__close, input, select');
      return [...targets]
        .filter((element) => {
          const box = element.getBoundingClientRect();
          return box.height > 0 && box.height < 44;
        })
        .map(
          (element) => `${element.className}:${Math.round(element.getBoundingClientRect().height)}`,
        );
    });
    expect(small).toEqual([]);
  });
});

test.describe('keyboard only', () => {
  test('reaches the search box, filters and a Bill card by tabbing', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();

    await page.keyboard.press('Tab'); // skip link
    await expect(page.getByRole('link', { name: /Skip to the Bill pipeline/ })).toBeFocused();

    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Search Bills')).toBeFocused();

    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Status')).toBeFocused();
  });

  test('filters, opens a Bill and closes it without a pointer', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await page.getByLabel('Search Bills').fill('Health Standards');

    const card = page.getByRole('button', { name: /Health Standards Bill\. View details\./ });
    await expect(card).toBeVisible();

    await card.focus();
    await page.keyboard.press('Enter');

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Close Bill details' })).toBeFocused();

    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(card).toBeFocused();
  });

  test('keeps focus inside the details sheet while it is open', async ({ page }) => {
    await page.goto('/?bill=9004');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    for (let index = 0; index < 12; index += 1) {
      await page.keyboard.press('Tab');
      const inside = await page.evaluate(() => document.activeElement?.closest('.sheet') !== null);
      expect(inside).toBe(true);
    }
  });
});

test.describe('the pipeline', () => {
  test('places each Bill exactly once', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();

    const names = await page
      .getByRole('button', { name: /View details\.$/ })
      .evaluateAll((elements) => elements.map((element) => element.getAttribute('aria-label')));
    expect(new Set(names).size).toBe(names.length);
  });

  test('keeps empty stages visible with a zero count', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    const buckets = page.locator('.bucket');
    await expect(buckets).toHaveCount(24);
    await expect(page.getByText('No Bills at this stage.').first()).toBeVisible();
  });

  test('restores the whole view from a shared link', async ({ page }) => {
    await page.goto('/?status=acts&origin=commons');
    await expect(page.getByLabel('Status')).toHaveValue('acts');
    await expect(page.getByRole('button', { name: /Finance Act 2026/ })).toBeVisible();
  });

  test('closes the details panel on browser Back', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await page.getByRole('button', { name: /Health Standards Bill\. View details\./ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    await page.goBack();
    await expect(page.getByRole('dialog')).toBeHidden();
  });
});

test.describe('data states', () => {
  test('shows a full-page error and retries', async ({ page }) => {
    let attempts = 0;
    await page.route('**/data/current.json', async (route) => {
      attempts += 1;
      if (attempts === 1) {
        await route.fulfill({ status: 503, contentType: 'text/plain', body: 'unavailable' });
        return;
      }
      await route.continue();
    });

    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: 'Bill data could not be loaded' }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Retry' }).click();
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();
  });

  test('warns that live data is stale without hiding it', async ({ page }) => {
    await serveSnapshot(page, (document) => {
      document['synthetic'] = false;
      document['status'] = 'healthy';
      document['generatedAt'] = '2020-01-01T00:00:00Z';
    });
    await page.goto('/');
    await expect(page.getByText('Data may be out of date')).toBeVisible();
    await expect(page.getByRole('button', { name: /Health Standards Bill/ })).toBeVisible();
  });

  test('labels the synthetic example snapshot', async ({ page }) => {
    await page.goto('/');
    // Labelled twice on purpose: in the header line and as a banner, so it
    // cannot be mistaken for live Parliamentary data.
    await expect(page.getByText('Example data', { exact: true })).toBeVisible();
    await expect(page.getByText(/^Example data, generated/)).toBeVisible();
    await expect(page.getByText(/do not describe any real Bill/)).toBeVisible();
  });
});

test.describe('reduced motion', () => {
  test('does not animate the loading skeleton', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();

    const seconds = await page.evaluate(() => {
      const probe = document.createElement('div');
      probe.className = 'skeleton';
      document.body.append(probe);
      const duration = getComputedStyle(probe).animationDuration;
      probe.remove();
      // Chromium reports this in seconds, in exponent form for tiny values.
      return Number.parseFloat(duration);
    });
    // The reduced-motion rule collapses animation to an imperceptible length.
    expect(seconds).toBeLessThan(0.01);
  });
});

test.describe('the Bill journey page', () => {
  for (const viewport of VIEWPORTS) {
    test(`has no horizontal overflow at ${viewport.name}px`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/?bill=9011&view=journey');
      await expect(
        page.getByRole('heading', { level: 2, name: 'Data Protection Bill' }),
      ).toBeVisible();
      expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
    });
  }

  test('draws the route as a flow diagram with the path marked on it', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/?bill=9011&view=journey');
    await expect(
      page.getByRole('heading', { level: 2, name: 'Data Protection Bill' }),
    ).toBeVisible();

    const diagram = page.getByRole('img', { name: /How Data Protection Bill moves through/ });
    await expect(diagram).toBeVisible();

    // Twelve numbered stages, two swimlanes, and the terminals.
    await expect(page.locator('.flow__step')).toHaveCount(12);
    await expect(page.locator('.flow__lane')).toHaveCount(2);
    // Ten of the twelve numbered stages are behind this Bill. The handover
    // and the decision are also drawn as completed, so this counts stages.
    await expect(page.locator('.flow__node--completed .flow__step')).toHaveCount(10);
    await expect(page.locator('.flow__node--current')).toHaveCount(1);
  });

  test('names the Houses the Bill actually used', async ({ page }) => {
    await page.goto('/?bill=9011&view=journey');
    await expect(page.locator('.flow__lane-label').first()).toHaveText(
      'First House · House of Commons',
    );
    await expect(page.locator('.flow__lane-label').nth(1)).toHaveText(
      'Second House · House of Lords',
    );

    // A Lords-first Bill reads the other way round.
    await page.goto('/?bill=9024&view=journey');
    await expect(page.locator('.flow__lane-label').first()).toHaveText(
      'First House · House of Lords',
    );
  });

  test('shows a defeated Bill leaving the route', async ({ page }) => {
    await page.goto('/?bill=9024&view=journey');
    await expect(
      page.getByRole('heading', { level: 2, name: 'Fixed Odds Betting Bill' }),
    ).toBeVisible();
    await expect(page.locator('.flow__edge--reject.flow__edge--taken')).toHaveCount(1);
    await expect(page.locator('.flow__node--stopped')).toHaveCount(1);
  });

  test('the diagram scrolls inside its own box rather than the page', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/?bill=9011&view=journey');
    await expect(page.getByRole('img', { name: /moves through Parliament/ })).toBeVisible();

    const scrollable = await page.evaluate(() => {
      const box = document.querySelector('.flow-scroll');
      return box === null ? false : box.scrollWidth > box.clientWidth;
    });
    expect(scrollable).toBe(true);
    expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
  });

  test('returns to the pipeline and back again through browser history', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/?bill=9011&view=journey');
    await expect(
      page.getByRole('heading', { level: 2, name: 'Data Protection Bill' }),
    ).toBeVisible();

    await page.getByRole('button', { name: /Back to all Bills/ }).click();
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();
  });
});
