import { useCallback, useRef, useState } from 'react';

import { ApiError, analyseDocument, deleteDocument, uploadDocument } from '@/api/client';
import type { DocumentAnalysis, DocumentSummary } from '@/api/types';

/** Where the session is in the upload-then-analyse flow. */
export type SessionPhase = 'idle' | 'uploading' | 'analysing' | 'ready' | 'error';

export interface DocumentSession {
  readonly phase: SessionPhase;
  readonly summary: DocumentSummary | null;
  readonly analysis: DocumentAnalysis | null;
  readonly error: string | null;
  submit: (file: File) => Promise<void>;
  /** Re-run analysis on the document already uploaded, without re-uploading. */
  retryAnalysis: () => Promise<void>;
  reset: () => Promise<void>;
}

/** Message shown when a failure carries no client-safe explanation. */
const FALLBACK_ERROR = 'Something went wrong. Please try again.';

function messageFor(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof DOMException && error.name === 'AbortError') {
    return 'The upload was cancelled.';
  }
  return FALLBACK_ERROR;
}

/**
 * Owns the lifecycle of one uploaded document.
 *
 * Upload and analysis run under a single abort controller, so starting a second
 * document cancels the first in flight rather than letting two responses race
 * to set state. The previous document is deleted from the server as soon as it
 * is replaced, rather than being left to expire.
 */
export function useDocumentSession(
  onAnnounce: (message: string) => void,
): DocumentSession {
  const [phase, setPhase] = useState<SessionPhase>('idle');
  const [summary, setSummary] = useState<DocumentSummary | null>(null);
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const currentIdRef = useRef<string | null>(null);

  const runAnalysis = useCallback(
    async (documentId: string, controller: AbortController) => {
      const result = await analyseDocument(documentId, controller.signal);
      if (controller.signal.aborted) return;
      setAnalysis(result);
      setPhase('ready');
      onAnnounce(
        `Analysis complete. ${result.findings.length} clauses to review and ` +
          `${result.obligations.length} obligations found. Results are below.`,
      );
    },
    [onAnnounce],
  );

  const submit = useCallback(
    async (file: File) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const previousId = currentIdRef.current;
      if (previousId) void deleteDocument(previousId);

      setError(null);
      setAnalysis(null);
      setSummary(null);
      setPhase('uploading');
      onAnnounce(`Uploading ${file.name}.`);

      try {
        const uploaded = await uploadDocument(file, controller.signal);
        if (controller.signal.aborted) return;
        currentIdRef.current = uploaded.document_id;
        setSummary(uploaded);
        setPhase('analysing');
        onAnnounce(`${uploaded.filename} uploaded. Reading the document now.`);

        await runAnalysis(uploaded.document_id, controller);
      } catch (caught) {
        if (controller.signal.aborted) return;
        const message = messageFor(caught);
        setError(message);
        setPhase('error');
        onAnnounce(`Something went wrong. ${message}`);
      }
    },
    [onAnnounce, runAnalysis],
  );

  const retryAnalysis = useCallback(async () => {
    const documentId = currentIdRef.current;
    if (!documentId) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setPhase('analysing');
    onAnnounce('Trying the analysis again.');
    try {
      await runAnalysis(documentId, controller);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const message = messageFor(caught);
      setError(message);
      setPhase('error');
      onAnnounce(`Something went wrong. ${message}`);
    }
  }, [onAnnounce, runAnalysis]);

  const reset = useCallback(async () => {
    abortRef.current?.abort();
    const documentId = currentIdRef.current;
    currentIdRef.current = null;
    setPhase('idle');
    setSummary(null);
    setAnalysis(null);
    setError(null);
    onAnnounce('Document cleared. You can upload another document.');
    if (documentId) await deleteDocument(documentId);
  }, [onAnnounce]);

  return { phase, summary, analysis, error, submit, retryAnalysis, reset };
}
