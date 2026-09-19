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
  /**
   * Re-upload the current file after the server has forgotten it (expiry or
   * restart), returning the new document id, or null if there is no file.
   */
  recover: () => Promise<string | null>;
  reset: () => Promise<void>;
}

/** Message shown when a failure carries no client-safe explanation. */
const FALLBACK_ERROR = 'Something went wrong. Please try again.';

/** Whether the server reported that the document is no longer held. */
export function isExpired(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'document_not_found';
}

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
export function useDocumentSession(onAnnounce: (message: string) => void): DocumentSession {
  const [phase, setPhase] = useState<SessionPhase>('idle');
  const [summary, setSummary] = useState<DocumentSummary | null>(null);
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const currentIdRef = useRef<string | null>(null);
  // The browser keeps the file it already holds. Documents live only in
  // server memory, so when they expire the page can restore them itself
  // rather than leaving results on screen that nothing backs any more.
  const fileRef = useRef<File | null>(null);

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
      fileRef.current = file;

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

  const recover = useCallback(async (): Promise<string | null> => {
    const file = fileRef.current;
    if (!file) return null;
    onAnnounce('Your document had expired from memory. Restoring it.');
    const uploaded = await uploadDocument(file);
    currentIdRef.current = uploaded.document_id;
    setSummary(uploaded);
    return uploaded.document_id;
  }, [onAnnounce]);

  const retryAnalysis = useCallback(async () => {
    let documentId = currentIdRef.current;
    if (!documentId) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setPhase('analysing');
    onAnnounce('Trying the analysis again.');
    try {
      try {
        await runAnalysis(documentId, controller);
      } catch (caught) {
        if (!isExpired(caught)) throw caught;
        documentId = await recover();
        if (!documentId) throw caught;
        await runAnalysis(documentId, controller);
      }
    } catch (caught) {
      if (controller.signal.aborted) return;
      const message = messageFor(caught);
      setError(message);
      setPhase('error');
      onAnnounce(`Something went wrong. ${message}`);
    }
  }, [onAnnounce, recover, runAnalysis]);

  const reset = useCallback(async () => {
    abortRef.current?.abort();
    const documentId = currentIdRef.current;
    currentIdRef.current = null;
    fileRef.current = null;
    setPhase('idle');
    setSummary(null);
    setAnalysis(null);
    setError(null);
    onAnnounce('Document cleared. You can upload another document.');
    if (documentId) await deleteDocument(documentId);
  }, [onAnnounce]);

  return {
    phase,
    summary,
    analysis,
    error,
    submit,
    retryAnalysis,
    recover,
    reset,
  };
}
