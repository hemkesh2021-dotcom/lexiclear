import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SAMPLE = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../samples/sample-rental-agreement.txt',
);

const WCAG_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

/**
 * Accessibility is audited in a real browser, where axe can evaluate the rules
 * jsdom cannot: colour contrast, computed focus order and target size all need
 * layout and painting. The suite runs in both colour schemes, because a theme
 * that only meets contrast in one of them meets it in neither.
 */
test.describe('accessibility', () => {
  async function audit(page: import('@playwright/test').Page) {
    return new AxeBuilder({ page }).withTags(WCAG_AA).analyze();
  }

  for (const colorScheme of ['light', 'dark'] as const) {
    test(`the upload view meets WCAG 2.1 AA in ${colorScheme} mode`, async ({ page }) => {
      await page.emulateMedia({ colorScheme });
      await page.goto('/');
      const results = await audit(page);
      expect(results.violations).toEqual([]);
    });

    test(`the results view meets WCAG 2.1 AA in ${colorScheme} mode`, async ({ page }) => {
      await page.emulateMedia({ colorScheme });
      await page.goto('/');
      await page.getByLabel(/Choose a document/).setInputFiles(SAMPLE);
      await expect(page.getByRole('heading', { name: /Clauses to read closely/ })).toBeVisible({
        timeout: 30_000,
      });
      const results = await audit(page);
      expect(results.violations).toEqual([]);
    });
  }

  test('the page still works with animation suppressed', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    await expect(page.getByLabel(/Choose a document/)).toBeVisible();
    const results = await audit(page);
    expect(results.violations).toEqual([]);
  });

  test('content reflows at 320 CSS pixels without horizontal scrolling', async ({ page }) => {
    // WCAG 1.4.10 Reflow.
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto('/');
    await page.getByLabel(/Choose a document/).setInputFiles(SAMPLE);
    await expect(page.getByRole('heading', { name: /Clauses to read closely/ })).toBeVisible({
      timeout: 30_000,
    });

    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    );
    expect(overflows).toBe(false);
  });

  test('text remains readable at 200% zoom', async ({ page }) => {
    // WCAG 1.4.4 Resize text.
    await page.goto('/');
    await page.addStyleTag({ content: 'html { font-size: 200% }' });
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const results = await audit(page);
    expect(results.violations).toEqual([]);
  });

  test('every interactive control has an accessible name', async ({ page }) => {
    await page.goto('/');

    // `element.labels` and the ARIA attributes are read directly rather than
    // through a `label[for=...]` selector: React 19 generates ids containing
    // guillemets, which are legal in HTML but not in an unescaped CSS selector.
    const unnamed = await page.evaluate(() => {
      const controls = document.querySelectorAll<HTMLElement>(
        'button, a[href], input, textarea, select',
      );
      return [...controls]
        .filter((element) => {
          const labels = (element as HTMLInputElement).labels;
          const named =
            element.getAttribute('aria-label') ??
            (labels && labels.length > 0 ? labels[0]?.textContent : null) ??
            element.textContent;
          return !named?.trim();
        })
        .map((element) => element.outerHTML.slice(0, 120));
    });

    expect(unnamed).toEqual([]);
  });
});
