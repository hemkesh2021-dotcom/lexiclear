import { useCallback } from 'react';

import { AnalysisPanel } from '@/components/AnalysisPanel';
import { ChatPanel } from '@/components/ChatPanel';
import { Icon } from '@/components/Icon';
import { LiveRegion } from '@/components/LiveRegion';
import { SkipLink } from '@/components/SkipLink';
import { UploadPanel } from '@/components/UploadPanel';
import { useAnnouncer } from '@/hooks/useAnnouncer';
import { useDocumentSession } from '@/hooks/useDocumentSession';

/**
 * Application shell.
 *
 * The page is a single view with two states rather than a router: there is one
 * task, and a URL change would lose the in-memory document anyway. Landmarks
 * (`banner`, `main`, `contentinfo`) are present in every state so assistive
 * technology has a stable structure to navigate.
 */
export function App(): React.ReactElement {
  const announcer = useAnnouncer();
  const session = useDocumentSession(announcer.announce);
  const { submit, reset } = session;

  const handleSubmit = useCallback(
    (file: File) => {
      void submit(file);
    },
    [submit],
  );

  const handleClear = useCallback(() => {
    void reset();
  }, [reset]);

  const { analysis, summary } = session;
  const showResults = session.phase === 'ready' && analysis !== null && summary !== null;

  return (
    <div className="app">
      <SkipLink />
      <LiveRegion message={announcer.message} nonce={announcer.nonce} />

      <header className="app__header">
        <p className="brand">
          <span className="brand__mark">
            <Icon name="scales" size={22} />
          </span>
          LexiClear
        </p>
        <p className="panel__hint">
          Understand a legal document before you sign it. Information, not legal advice.
        </p>
      </header>

      <main className="app__main" id="main-content" tabIndex={-1}>
        <h1>
          {showResults
            ? 'What your document says'
            : 'Upload a contract, policy or notice to see what it actually says'}
        </h1>

        {showResults ? (
          <div className="workspace">
            <AnalysisPanel analysis={analysis} summary={summary} onClear={handleClear} />
            <ChatPanel documentId={summary.document_id} onAnnounce={announcer.announce} />
          </div>
        ) : (
          <div className="stack">
            <p>
              LexiClear reads the document you upload, explains it in plain language, and
              points out the clauses that deserve your attention. Every finding quotes your
              document word for word; anything it cannot quote is discarded rather than
              shown.
            </p>
            <UploadPanel
              phase={session.phase}
              error={session.error}
              onSubmit={handleSubmit}
            />
          </div>
        )}
      </main>

      <footer className="app__footer">
        <p>
          LexiClear provides general information to help you understand a document. It is
          not legal advice and does not create a lawyer-client relationship. Documents are
          held in memory for 30 minutes and are never written to disk.
        </p>
      </footer>
    </div>
  );
}
