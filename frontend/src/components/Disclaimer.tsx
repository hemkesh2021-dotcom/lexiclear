interface DisclaimerProps {
  readonly text: string;
}

/**
 * The standing notice that LexiClear informs rather than advises.
 *
 * Rendered as a `note` landmark so screen-reader users can jump to it, and
 * repeated at the foot of every results view rather than shown once at upload.
 */
export function Disclaimer({ text }: DisclaimerProps): React.ReactElement {
  return (
    <aside className="disclaimer" aria-label="Important notice">
      <strong>This is information, not legal advice. </strong>
      {text}
    </aside>
  );
}
