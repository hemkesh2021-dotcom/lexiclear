import { useCallback, useEffect, useId, useRef, useState } from 'react';

import { ApiError, streamAnswer, type AnswerStreamHandlers } from '@/api/client';
import type { Citation, Exchange } from '@/api/types';
import { Icon } from '@/components/Icon';
import { StatusMessage } from '@/components/StatusMessage';
import { isExpired } from '@/hooks/useDocumentSession';

interface ChatPanelProps {
  readonly documentId: string;
  readonly onAnnounce: (message: string) => void;
  /** Restores an expired document and returns its new id. */
  readonly onDocumentExpired?: (() => Promise<string | null>) | undefined;
}

const SUGGESTIONS = [
  'How can this agreement be ended, and by whom?',
  'What am I required to pay, and by when?',
  'What happens if I miss a deadline?',
  'Which clauses limit what I can claim?',
] as const;

const MAX_QUESTION_LENGTH = 1000;

function createId(): string {
  return `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Grounded question-and-answer over the uploaded document.
 *
 * The transcript is a `<ul>` inside a `role="log"` region with
 * `aria-live="polite"`, which is the pattern assistive technology expects for
 * an appended conversation: new entries are announced, earlier ones are not
 * re-read. Answer text is *not* announced token by token - that would produce a
 * stutter of single words - so the region announces the question immediately
 * and the completed answer once the stream closes.
 */
export function ChatPanel({
  documentId,
  onAnnounce,
  onDocumentExpired,
}: ChatPanelProps): React.ReactElement {
  const fieldId = useId();
  const hintId = useId();
  const [question, setQuestion] = useState('');
  const [exchanges, setExchanges] = useState<readonly Exchange[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const shouldRefocusRef = useRef(false);

  // The field is disabled while an answer streams, and calling focus() on a
  // disabled element does nothing. Restoring focus therefore has to wait for
  // the re-render that re-enables it, or a keyboard user is left stranded at
  // the top of the document after every question.
  useEffect(() => {
    if (!isStreaming && shouldRefocusRef.current) {
      shouldRefocusRef.current = false;
      fieldRef.current?.focus();
    }
  }, [isStreaming]);

  const update = useCallback((id: string, patch: Partial<Exchange>) => {
    setExchanges((previous) =>
      previous.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    );
  }, []);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      const id = createId();
      setExchanges((previous) => [
        ...previous,
        {
          id,
          question: trimmed,
          answer: '',
          citations: [],
          status: 'streaming',
        },
      ]);
      setQuestion('');
      setIsStreaming(true);
      onAnnounce('Looking for an answer in your document.');

      let answer = '';
      let citations: readonly Citation[] = [];

      const handlers: AnswerStreamHandlers = {
        onCitations: (received) => {
          citations = received;
          update(id, { citations: received });
        },
        onToken: (fragment) => {
          answer += fragment;
          update(id, { answer });
        },
        onError: (message) => {
          update(id, { status: 'error', error: message });
          onAnnounce(`The answer could not be completed. ${message}`);
        },
        onDone: () => {
          update(id, { status: 'complete' });
          onAnnounce(
            `Answer ready, citing ${citations.length} ${
              citations.length === 1 ? 'passage' : 'passages'
            }. ${answer}`,
          );
        },
      };

      try {
        try {
          await streamAnswer(documentId, trimmed, handlers);
        } catch (caught) {
          // The request is refused before any event is sent, so a retry
          // against the restored document cannot duplicate partial output.
          const restoredId = isExpired(caught) ? await onDocumentExpired?.() : null;
          if (!restoredId) throw caught;
          await streamAnswer(restoredId, trimmed, handlers);
        }
      } catch (caught) {
        const message =
          caught instanceof ApiError ? caught.message : 'The answer could not be completed.';
        update(id, { status: 'error', error: message });
        onAnnounce(message);
      } finally {
        shouldRefocusRef.current = true;
        setIsStreaming(false);
      }
    },
    [documentId, isStreaming, onAnnounce, onDocumentExpired, update],
  );

  return (
    <section className="panel chat" aria-labelledby="chat-heading">
      <div className="panel__header">
        <h2 id="chat-heading">
          <Icon name="message" /> Ask about this document
        </h2>
        <p className="panel__hint">Answers come only from your document, with citations.</p>
      </div>

      <div className="chat__log" role="log" aria-live="polite" aria-labelledby="chat-heading">
        {exchanges.length === 0 ? (
          <p className="panel__hint">
            No questions yet. Try one of the suggestions below, or type your own.
          </p>
        ) : (
          <ul className="stack" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {exchanges.map((exchange) => (
              <li key={exchange.id} className="exchange">
                <p className="exchange__question">
                  <span className="visually-hidden">You asked: </span>
                  {exchange.question}
                </p>

                {exchange.status === 'error' ? (
                  <p className="exchange__error" role="alert">
                    {exchange.error}
                  </p>
                ) : (
                  <p className="exchange__answer">
                    <span className="visually-hidden">Answer: </span>
                    {exchange.answer}
                    {exchange.status === 'streaming' && exchange.answer === '' && (
                      <span className="panel__hint">Searching the document…</span>
                    )}
                  </p>
                )}

                {exchange.citations.length > 0 && (
                  <details className="citations">
                    <summary className="citations__summary">
                      {exchange.citations.length} source{' '}
                      {exchange.citations.length === 1 ? 'passage' : 'passages'} from your document
                    </summary>
                    {exchange.citations.map((citation) => (
                      <div key={`${citation.label}-${citation.start}`} className="citation">
                        <span className="citation__label">{citation.label}</span>
                        <span>{citation.quote}</span>
                      </div>
                    ))}
                  </details>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <form
        className="chat__composer"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor={fieldId}>
            Your question
          </label>
          <textarea
            ref={fieldRef}
            id={fieldId}
            className="field__control"
            rows={3}
            maxLength={MAX_QUESTION_LENGTH}
            value={question}
            aria-describedby={hintId}
            disabled={isStreaming}
            onChange={(event) => {
              setQuestion(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void ask(question);
              }
            }}
          />
          <p className="field__hint" id={hintId}>
            Press Control and Enter, or Command and Enter, to send. Up to {MAX_QUESTION_LENGTH}{' '}
            characters.
          </p>
        </div>

        <ul className="suggestions">
          {SUGGESTIONS.map((suggestion) => (
            <li key={suggestion}>
              <button
                type="button"
                className="button"
                disabled={isStreaming}
                onClick={() => {
                  void ask(suggestion);
                }}
              >
                {suggestion}
              </button>
            </li>
          ))}
        </ul>

        <div>
          <button
            type="submit"
            className="button button--primary"
            disabled={isStreaming || question.trim().length < 3}
          >
            {isStreaming ? 'Finding an answer…' : 'Ask question'}
          </button>
        </div>
      </form>

      {isStreaming && (
        <StatusMessage tone="info" busy>
          Searching your document and drafting an answer.
        </StatusMessage>
      )}
    </section>
  );
}
