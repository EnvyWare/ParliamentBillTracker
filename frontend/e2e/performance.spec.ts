import { gzipSync } from 'node:zlib';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

const DIST = fileURLToPath(new URL('../dist/assets', import.meta.url));

const JS_BUDGET_BYTES = 200 * 1024;
const CSS_BUDGET_BYTES = 50 * 1024;

function gzippedSize(extension: string): number {
  return readdirSync(DIST)
    .filter((name) => name.endsWith(extension))
    .reduce((total, name) => total + gzipSync(readFileSync(`${DIST}/${name}`)).length, 0);
}

test.describe('budgets', () => {
  test('initial JavaScript stays under 200 KB gzip', () => {
    const size = gzippedSize('.js');
    expect(size, `JavaScript is ${Math.round(size / 1024)} KB gzip`).toBeLessThan(JS_BUDGET_BYTES);
  });

  test('CSS stays under 50 KB gzip', () => {
    const size = gzippedSize('.css');
    expect(size, `CSS is ${Math.round(size / 1024)} KB gzip`).toBeLessThan(CSS_BUDGET_BYTES);
  });
});

test.describe('no third-party runtime origin', () => {
  test('the browser never requests the Parliament API', async ({ page }) => {
    const external: string[] = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
        external.push(request.url());
      }
    });

    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();
    await page.getByRole('button', { name: /Health Standards Bill\. View details\./ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    expect(external).toEqual([]);
  });

  test('loads no remote font, analytics script or image', async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();

    const remoteAssets = await page.evaluate(() => {
      const isRemote = (value: string | null): boolean =>
        value !== null && /^https?:\/\//.test(value) && !value.startsWith(window.location.origin);
      const images = [...document.querySelectorAll('img')].map((element) => element.src);
      const styles = [...document.querySelectorAll('link[rel="stylesheet"]')].map((element) =>
        element.getAttribute('href'),
      );
      const scripts = [...document.querySelectorAll('script[src]')].map((element) =>
        element.getAttribute('src'),
      );
      return [...images, ...styles, ...scripts].filter(isRemote);
    });
    expect(remoteAssets).toEqual([]);
  });

  test('renders no image element at all', async ({ page }) => {
    // No member photograph and no Parliamentary imagery is ever displayed.
    await page.goto('/?bill=9004');
    await expect(page.getByRole('dialog')).toBeVisible();
    expect(await page.locator('img').count()).toBe(0);
  });
});

test.describe('interaction speed', () => {
  test('applies a filter well within 100ms on the expected dataset', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();

    const elapsed = await page.evaluate(() => {
      const select = document.querySelector<HTMLSelectElement>('select');
      if (select === null) return 0;
      const started = performance.now();
      select.value = 'all';
      select.dispatchEvent(new Event('change', { bubbles: true }));
      return performance.now() - started;
    });
    expect(elapsed).toBeLessThan(100);
  });

  test('keeps layout shift low on a mid-range mobile profile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();

    const shift = await page.evaluate(
      () =>
        new Promise<number>((resolve) => {
          let total = 0;
          const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
              const layoutShift = entry as PerformanceEntry & {
                value: number;
                hadRecentInput: boolean;
              };
              if (!layoutShift.hadRecentInput) total += layoutShift.value;
            }
          });
          observer.observe({ type: 'layout-shift', buffered: true });
          setTimeout(() => {
            observer.disconnect();
            resolve(total);
          }, 1000);
        }),
    );
    expect(shift).toBeLessThan(0.1);
  });
});
