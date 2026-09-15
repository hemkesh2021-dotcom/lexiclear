interface LiveRegionProps {
  readonly message: string;
  readonly nonce: number;
}

/**
 * A polite live region announcing progress to assistive technology.
 *
 * `aria-live="polite"` waits for the user to finish what they are doing;
 * `aria-atomic` makes the whole message read as one utterance rather than as a
 * diff. The nonce guarantees the node's text changes even when the wording
 * repeats, which is what forces a re-announcement.
 */
export function LiveRegion({ message, nonce }: LiveRegionProps): React.ReactElement {
  return (
    <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
      {message}
      <span aria-hidden="true">{nonce > 0 ? '​'.repeat(nonce % 5) : ''}</span>
    </div>
  );
}
