import { Icon, type IconName } from '@/components/Icon';

export type StatusTone = 'info' | 'error' | 'success';

interface StatusMessageProps {
  readonly tone: StatusTone;
  readonly children: React.ReactNode;
  readonly busy?: boolean;
}

const ICONS: Record<StatusTone, IconName> = {
  info: 'clock',
  error: 'alert',
  success: 'check',
};

/**
 * An inline status message.
 *
 * Errors use `role="alert"` so they interrupt and are read immediately; other
 * tones use `role="status"`, which waits politely. The tone is carried by an
 * icon and wording as well as colour, so it survives a monochrome display.
 */
export function StatusMessage({
  tone,
  children,
  busy = false,
}: StatusMessageProps): React.ReactElement {
  return (
    <p className={`status status--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {busy ? <span className="spinner" /> : <Icon name={ICONS[tone]} />}
      <span>{children}</span>
    </p>
  );
}
