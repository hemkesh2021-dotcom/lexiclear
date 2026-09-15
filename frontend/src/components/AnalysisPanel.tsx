import type { DocumentAnalysis, DocumentSummary } from '@/api/types';
import { Disclaimer } from '@/components/Disclaimer';
import { FindingCard } from '@/components/FindingCard';
import { Icon } from '@/components/Icon';

interface AnalysisPanelProps {
  readonly analysis: DocumentAnalysis;
  readonly summary: DocumentSummary;
  readonly onClear: () => void;
}

/**
 * The analysis results.
 *
 * Structured as a sequence of `<section>` landmarks with real headings so that
 * a screen-reader user can move between "what this document is", "clauses to
 * read closely", "what you have to do" and "what to ask a lawyer" using heading
 * navigation, rather than having to listen through the whole page.
 */
export function AnalysisPanel({
  analysis,
  summary,
  onClear,
}: AnalysisPanelProps): React.ReactElement {
  return (
    <div className="stack">
      <section className="panel" aria-labelledby="summary-heading">
        <div className="panel__header">
          <h2 id="summary-heading">{analysis.document_type}</h2>
          <button type="button" className="button button--quiet" onClick={onClear}>
            <Icon name="trash" size={16} /> Clear document
          </button>
        </div>

        <dl className="meta-grid">
          <div>
            <dt>File</dt>
            <dd>{summary.filename}</dd>
          </div>
          <div>
            <dt>Clauses flagged</dt>
            <dd>{analysis.findings.length}</dd>
          </div>
          <div>
            <dt>Your obligations</dt>
            <dd>{analysis.obligations.length}</dd>
          </div>
          <div>
            <dt>Passages indexed</dt>
            <dd>{summary.chunk_count}</dd>
          </div>
        </dl>

        <p>{analysis.plain_language_summary}</p>

        {analysis.parties.length > 0 && (
          <>
            <h3>Parties</h3>
            <ul className="tag-list">
              {analysis.parties.map((party) => (
                <li key={party} className="badge badge--category">
                  {party}
                </li>
              ))}
            </ul>
          </>
        )}

        {analysis.key_dates.length > 0 && (
          <>
            <h3>Dates and deadlines</h3>
            <ul className="tag-list">
              {analysis.key_dates.map((date) => (
                <li key={date} className="badge badge--low">
                  {date}
                </li>
              ))}
            </ul>
          </>
        )}

        {summary.truncated && (
          <p className="panel__hint">
            This document was longer than the size we analyse in one pass, so the analysis
            covers the first part of it. Split the file and upload the remainder to review
            the rest.
          </p>
        )}
        {analysis.unverified_finding_count > 0 && (
          <p className="panel__hint">
            {analysis.unverified_finding_count} additional{' '}
            {analysis.unverified_finding_count === 1 ? 'observation was' : 'observations were'}{' '}
            discarded because {analysis.unverified_finding_count === 1 ? 'it' : 'they'} could
            not be matched to wording in your document. Only findings quoting the document
            verbatim are shown.
          </p>
        )}
      </section>

      <section className="panel" aria-labelledby="findings-heading">
        <div className="panel__header">
          <h2 id="findings-heading">
            <Icon name="alert" /> Clauses to read closely
          </h2>
          <p className="panel__hint">Ordered by how much attention they deserve.</p>
        </div>
        {analysis.findings.length === 0 ? (
          <p>No clauses could be verified against the document text.</p>
        ) : (
          analysis.findings.map((finding) => (
            <FindingCard key={`${finding.title}-${finding.quote.slice(0, 24)}`} finding={finding} />
          ))
        )}
      </section>

      {analysis.obligations.length > 0 && (
        <section className="panel" aria-labelledby="obligations-heading">
          <div className="panel__header">
            <h2 id="obligations-heading">
              <Icon name="list" /> What this document requires
            </h2>
          </div>
          <ul className="checklist">
            {analysis.obligations.map((item) => (
              <li key={`${item.who}-${item.what}`}>
                <span className="checklist__who">{item.who}</span>
                <span>{item.what}</span>
                <span className="checklist__when">When: {item.when}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {analysis.questions_for_a_lawyer.length > 0 && (
        <section className="panel" aria-labelledby="lawyer-heading">
          <div className="panel__header">
            <h2 id="lawyer-heading">
              <Icon name="scales" /> Questions to put to a lawyer
            </h2>
            <p className="panel__hint">
              Take these to a qualified professional before you sign.
            </p>
          </div>
          <ul className="checklist">
            {analysis.questions_for_a_lawyer.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </section>
      )}

      <Disclaimer text={analysis.disclaimer} />
    </div>
  );
}
