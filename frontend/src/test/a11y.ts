import { expect } from 'vitest';
import { axe } from 'vitest-axe';

/**
 * Assert that a rendered tree has no axe-core accessibility violations.
 *
 * Written as a helper rather than as a custom matcher because a matcher would
 * need type augmentation that `vitest-axe` does not yet ship for Vitest 3, and
 * because this reports *which* rules failed and on which elements - a matcher's
 * message only says that something did.
 *
 * Colour contrast is not evaluated here: jsdom performs no layout or painting,
 * so axe skips that rule. Contrast is covered in the Playwright suite, which
 * runs the same audit in a real browser.
 */
export async function expectNoAxeViolations(container: Element): Promise<void> {
  const results = await axe(container);
  const summary = results.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact ?? 'unknown'}): ${violation.help} ` +
      `[${violation.nodes.map((node) => node.target.join(' ')).join(', ')}]`,
  );
  expect(summary, summary.join('\n')).toEqual([]);
}
