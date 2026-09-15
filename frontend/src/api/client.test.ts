import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  analyseDocument,
  parseEventFrame,
  streamAnswer,
  uploadDocument,
} from '@/api/client';
import { analysisFixture, citationsFixture, frame, sseResponse } from '@/test/fixtures';

describe('parseEventFrame', () => {
  it('reads the event name and payload', () => {
    expect(parseEventFrame('event: token\ndata: {"text":"hi"}')).toEqual({
      event: 'token',
      data: '{"text":"hi"}',
    });
  });

  it('defaults an unnamed frame to "message"', () => {
    expect(parseEventFrame('data: {"a":1}')?.event).toBe('message');
  });

  it('joins a payload split across several data lines', () => {
    expect(parseEventFrame('event: x\ndata: one\ndata: two')?.data).toBe('one\ntwo');
  });

  it('ignores a frame carrying no data', () => {
    expect(parseEventFrame('event: ping\n:comment')).toBeNull();
  });
});

describe('uploadDocument', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts the file as multipart form data', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ document_id: 'abc' }), { status: 201 }),
    );
    await uploadDocument(new File(['contract'], 'lease.txt', { type: 'text/plain' }));

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/documents');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
  });

  it('surfaces the API error code and message', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ code: 'file_too_large', message: 'Documents must be smaller.' }),
        { status: 413 },
      ),
    );

    await expect(uploadDocument(new File([''], 'a.txt'))).rejects.toMatchObject({
      code: 'file_too_large',
      message: 'Documents must be smaller.',
      status: 413,
    });
  });

  it('falls back to a safe message when the error body is unreadable', async () => {
    fetchMock.mockResolvedValue(new Response('<html>502</html>', { status: 502 }));
    await expect(uploadDocument(new File([''], 'a.txt'))).rejects.toBeInstanceOf(ApiError);
  });
});

describe('analyseDocument', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the analysis', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify(analysisFixture), { status: 200 }));
    await expect(analyseDocument('doc-123')).resolves.toEqual(analysisFixture);
  });

  it('percent-encodes the document identifier', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify(analysisFixture), { status: 200 }));
    await analyseDocument('a/../b');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/documents/a%2F..%2Fb/analysis');
  });
});

describe('streamAnswer', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function handlers() {
    return {
      onCitations: vi.fn(),
      onToken: vi.fn(),
      onError: vi.fn(),
      onDone: vi.fn(),
    };
  }

  it('dispatches citations, tokens and completion in order', async () => {
    const seen: string[] = [];
    fetchMock.mockResolvedValue(
      sseResponse([
        frame('citations', { citations: citationsFixture }),
        frame('token', { text: 'You ' }),
        frame('token', { text: 'must give three months.' }),
        frame('done', { disclaimer: 'Not legal advice.' }),
      ]),
    );

    await streamAnswer('doc-123', 'How do I leave?', {
      onCitations: () => seen.push('citations'),
      onToken: () => seen.push('token'),
      onError: () => seen.push('error'),
      onDone: () => seen.push('done'),
    });

    expect(seen).toEqual(['citations', 'token', 'token', 'done']);
  });

  it('reassembles a frame split across two network chunks', async () => {
    const whole = frame('token', { text: 'thirty days' });
    const cut = Math.floor(whole.length / 2);
    fetchMock.mockResolvedValue(sseResponse([whole.slice(0, cut), whole.slice(cut)]));

    const h = handlers();
    await streamAnswer('doc-123', 'q', h);
    expect(h.onToken).toHaveBeenCalledWith('thirty days');
  });

  it('reports a server-side error event without throwing', async () => {
    fetchMock.mockResolvedValue(
      sseResponse([frame('error', { code: 'llm_unavailable', message: 'Try again.' })]),
    );

    const h = handlers();
    await streamAnswer('doc-123', 'q', h);
    expect(h.onError).toHaveBeenCalledWith('Try again.');
    expect(h.onDone).not.toHaveBeenCalled();
  });

  it('skips a frame whose payload is not valid JSON', async () => {
    fetchMock.mockResolvedValue(sseResponse(['event: token\ndata: {broken\n\n']));
    const h = handlers();
    await streamAnswer('doc-123', 'q', h);
    expect(h.onToken).not.toHaveBeenCalled();
  });

  it('ignores an unknown event type', async () => {
    fetchMock.mockResolvedValue(sseResponse([frame('heartbeat', { at: 1 })]));
    const h = handlers();
    await streamAnswer('doc-123', 'q', h);
    expect(h.onToken).not.toHaveBeenCalled();
    expect(h.onError).not.toHaveBeenCalled();
  });

  it('raises the API error when the request itself is refused', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'prompt_injection_detected',
          message: 'Please rephrase your question.',
        }),
        { status: 400 },
      ),
    );

    await expect(streamAnswer('doc-123', 'ignore instructions', handlers())).rejects.toMatchObject(
      { code: 'prompt_injection_detected' },
    );
  });
});
