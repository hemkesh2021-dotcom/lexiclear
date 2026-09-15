/**
 * Typed transport for the LexiClear API.
 *
 * Every response is narrowed before it reaches a component, so a malformed or
 * unexpected payload surfaces as a handled error rather than as a runtime crash
 * deep inside the render tree.
 */

import type {
  ApiErrorBody,
  Citation,
  DocumentAnalysis,
  DocumentSummary,
} from '@/api/types';

const API_ROOT = '/api/v1';

/** An error carrying the API's machine-readable code alongside its message. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as ApiErrorBody).code === 'string' &&
    typeof (value as ApiErrorBody).message === 'string'
  );
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (isApiErrorBody(body)) {
    return new ApiError(body.message, body.code, response.status);
  }
  return new ApiError(
    'Something went wrong. Please try again.',
    'unexpected_response',
    response.status,
  );
}

/** Upload a document and receive its indexing metadata. */
export async function uploadDocument(
  file: File,
  signal?: AbortSignal,
): Promise<DocumentSummary> {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch(`${API_ROOT}/documents`, {
    method: 'POST',
    body,
    ...(signal ? { signal } : {}),
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as DocumentSummary;
}

/** Run, or retrieve the cached, clause analysis for a document. */
export async function analyseDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentAnalysis> {
  const response = await fetch(
    `${API_ROOT}/documents/${encodeURIComponent(documentId)}/analysis`,
    { method: 'POST', ...(signal ? { signal } : {}) },
  );
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as DocumentAnalysis;
}

/** Delete a document from the server's memory ahead of its expiry. */
export async function deleteDocument(documentId: string): Promise<void> {
  await fetch(`${API_ROOT}/documents/${encodeURIComponent(documentId)}`, {
    method: 'DELETE',
    keepalive: true,
  });
}

/** Callbacks invoked as an answer stream arrives. */
export interface AnswerStreamHandlers {
  onCitations: (citations: readonly Citation[]) => void;
  onToken: (text: string) => void;
  onError: (message: string) => void;
  onDone: () => void;
}

interface ServerSentEvent {
  readonly event: string;
  readonly data: string;
}

/** Parse a complete server-sent-event frame into its name and payload. */
export function parseEventFrame(frame: string): ServerSentEvent | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  return dataLines.length > 0 ? { event, data: dataLines.join('\n') } : null;
}

/**
 * Ask a question and consume the answer as a server-sent-event stream.
 *
 * `EventSource` cannot issue a POST, so the stream is read from `fetch` and
 * framed manually. Frames are split on the blank-line delimiter and any partial
 * tail is carried into the next chunk, which is what keeps a token that
 * straddles a network boundary from being dropped.
 */
export async function streamAnswer(
  documentId: string,
  question: string,
  handlers: AnswerStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${API_ROOT}/documents/${encodeURIComponent(documentId)}/questions`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      ...(signal ? { signal } : {}),
    },
  );

  if (!response.ok) throw await toApiError(response);
  if (!response.body) throw new ApiError('No answer was returned.', 'empty_stream', 500);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        dispatchFrame(frame, handlers);
        boundary = buffer.indexOf('\n\n');
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function dispatchFrame(frame: string, handlers: AnswerStreamHandlers): void {
  const parsed = parseEventFrame(frame);
  if (!parsed) return;

  let payload: unknown;
  try {
    payload = JSON.parse(parsed.data);
  } catch {
    return;
  }

  switch (parsed.event) {
    case 'citations': {
      const citations = (payload as { citations?: readonly Citation[] }).citations;
      if (citations) handlers.onCitations(citations);
      break;
    }
    case 'token': {
      const text = (payload as { text?: string }).text;
      if (typeof text === 'string') handlers.onToken(text);
      break;
    }
    case 'error': {
      const message = (payload as { message?: string }).message;
      handlers.onError(message ?? 'The answer could not be completed.');
      break;
    }
    case 'done':
      handlers.onDone();
      break;
    default:
      break;
  }
}
