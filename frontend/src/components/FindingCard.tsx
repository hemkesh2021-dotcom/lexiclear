import type { ClauseFinding, RiskLevel } from '@/api/types';
import { humaniseCategory } from '@/lib/format';

interface FindingCardProps {
  readonly finding: ClauseFinding;
}

const RISK_COLOURS: Record<RiskLevel, string> = {
  high: 'var(--accent-pink)',
  medium: 'var(--accent-amber)',
  low: 'var(--accent-indigo-strong)',
  informational: 'var(--border-strong)',
};

const RISK_WORDS: Record<RiskLevel, string> = {
  high: 'Read closely',
  medium: 'Worth checking',
  low: 'Standard',
  informational: 'Background',
};

/**
 * One clause the reader should know about.
 *
 * Risk is communicated three ways - a word, a border position, and a colour -
 * so it never depends on colour perception alone (WCAG 1.4.1). The quotation is
 * a real `<blockquote>` with `<cite>`, which gives screen-reader users the same
 * "this is the document's own wording" cue that the monospaced styling gives
 * sighted users.
 */
export function FindingCard({ finding }: FindingCardProps): React.ReactElement {
  return (
    <article
      className="finding"
      style={{ '--risk-colour': RISK_COLOURS[finding.risk] } as React.CSSProperties}
    >
      <div className="finding__head">
        <h3 className="finding__title">{finding.title}</h3>
        <p className="finding__meta">
          <span className={`badge badge--${finding.risk}`}>{RISK_WORDS[finding.risk]}</span>
          <span className="badge badge--category">{humaniseCategory(finding.category)}</span>
        </p>
      </div>

      <p>{finding.plain_language}</p>
      <p className="finding__why">
        <strong>Why it matters: </strong>
        {finding.why_it_matters}
      </p>

      <blockquote cite="#document-source">
        <span className="visually-hidden">Quoted from your document: </span>
        {finding.quote}
        {finding.source && (
          <cite className="visually-hidden">
            {` Characters ${finding.source.start} to ${finding.source.end} of the document.`}
          </cite>
        )}
      </blockquote>
    </article>
  );
}
