/**
 * Inline SVG icons.
 *
 * Icons are drawn from the same 24-unit grid and inherit `currentColor`, so
 * they follow the text they sit beside in both themes and in forced-colours
 * mode. Every icon is `aria-hidden`: it decorates a control that already has a
 * text label, and announcing it again would only add noise.
 */

const PATHS = {
  scales:
    'M12 3v18M7 21h10M12 6 5 9m7-3 7 3M5 9l-2.5 5a3.5 3.5 0 0 0 5 0L5 9Zm14 0-2.5 5a3.5 3.5 0 0 0 5 0L19 9Z',
  upload: 'M12 16V4m0 0L8 8m4-4 4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
  alert: 'M12 9v4m0 4h.01M10.3 3.9 2.4 17a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  check: 'M20 6 9 17l-5-5',
  message: 'M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-6.4A8 8 0 1 1 21 12Z',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-14v5l3 2',
  trash: 'M4 7h16M10 11v6m4-6v6M5 7l1 13a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-13M9 7V4h6v3',
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps {
  readonly name: IconName;
  readonly size?: number;
}

export function Icon({ name, size = 20 }: IconProps): React.ReactElement {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
