/**
 * Bypass block for keyboard and switch users (WCAG 2.4.1).
 *
 * Visually hidden until focused, at which point it slides into view as the
 * first tab stop on the page.
 */
export function SkipLink(): React.ReactElement {
  return (
    <a className="skip-link" href="#main-content">
      Skip to main content
    </a>
  );
}
