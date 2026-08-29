import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { Page } from '@playwright/test';

const SNAPSHOT_PATH = fileURLToPath(new URL('../public/data/current.json', import.meta.url));

export const VIEWPORTS = [
  { name: '1440', width: 1440, height: 900 },
  { name: '1024', width: 1024, height: 800 },
  { name: '768', width: 768, height: 900 },
  { name: '390', width: 390, height: 844 },
  { name: '320', width: 320, height: 800 },
] as const;

export function exampleDocument(): Record<string, unknown> {
  return JSON.parse(readFileSync(SNAPSHOT_PATH, 'utf8')) as Record<string, unknown>;
}

/** Serve a modified snapshot so a state can be reproduced deterministically. */
export async function serveSnapshot(
  page: Page,
  mutate: (document: Record<string, unknown>) => void,
): Promise<void> {
  const document = exampleDocument();
  mutate(document);
  await page.route('**/data/current.json', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(document),
    });
  });
}

/** Serve a failing response, so the error and cached states can be tested. */
export async function failSnapshot(page: Page, status = 503): Promise<void> {
  await page.route('**/data/current.json', async (route) => {
    await route.fulfill({ status, contentType: 'text/plain', body: 'unavailable' });
  });
}

/** Horizontal overflow of the page itself, in CSS pixels. */
export async function pageOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}
