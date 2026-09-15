import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useDocumentSession } from '@/hooks/useDocumentSession';
import { analysisFixture, summaryFixture } from '@/test/fixtures';

const fetchMock = vi.fn();

function happyPath(): void {
  fetchMock.mockImplementation((url: string) =>
    Promise.resolve(
      url.endsWith('/analysis')
        ? new Response(JSON.stringify(analysisFixture), { status: 200 })
        : new Response(JSON.stringify(summaryFixture), { status: 201 }),
    ),
  );
}

const file = () => new File(['contract'], 'lease.txt', { type: 'text/plain' });

describe('useDocumentSession', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('starts idle with nothing loaded', () => {
    const { result } = renderHook(() => useDocumentSession(vi.fn()));
    expect(result.current.phase).toBe('idle');
    expect(result.current.analysis).toBeNull();
  });

  it('moves through uploading and analysing to ready', async () => {
    happyPath();
    const announce = vi.fn();
    const { result } = renderHook(() => useDocumentSession(announce));

    await act(async () => {
      await result.current.submit(file());
    });

    expect(result.current.phase).toBe('ready');
    expect(result.current.analysis).toEqual(analysisFixture);
    expect(announce).toHaveBeenCalledWith(expect.stringContaining('Uploading'));
    expect(announce).toHaveBeenCalledWith(expect.stringContaining('Analysis complete'));
  });

  it('surfaces an upload failure as a client-safe message', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ code: 'unsupported_file_type', message: 'Only PDF, DOCX or text.' }),
        { status: 415 },
      ),
    );
    const { result } = renderHook(() => useDocumentSession(vi.fn()));

    await act(async () => {
      await result.current.submit(file());
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toBe('Only PDF, DOCX or text.');
  });

  it('surfaces an analysis failure without discarding the upload state', async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith('/analysis')
          ? new Response(
              JSON.stringify({ code: 'llm_unavailable', message: 'Try again shortly.' }),
              { status: 503 },
            )
          : new Response(JSON.stringify(summaryFixture), { status: 201 }),
      ),
    );
    const { result } = renderHook(() => useDocumentSession(vi.fn()));

    await act(async () => {
      await result.current.submit(file());
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toBe('Try again shortly.');
    expect(result.current.summary).not.toBeNull();
  });

  it('deletes the previous document when a new one is submitted', async () => {
    happyPath();
    const { result } = renderHook(() => useDocumentSession(vi.fn()));

    await act(async () => {
      await result.current.submit(file());
    });
    await act(async () => {
      await result.current.submit(file());
    });

    await waitFor(() => {
      const deletes = fetchMock.mock.calls.filter(
        (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
      );
      expect(deletes).toHaveLength(1);
    });
  });

  it('reports a cancelled upload rather than a generic failure', async () => {
    fetchMock.mockRejectedValue(new DOMException('aborted', 'AbortError'));
    const { result } = renderHook(() => useDocumentSession(vi.fn()));

    await act(async () => {
      await result.current.submit(file());
    });

    expect(result.current.error).toBe('The upload was cancelled.');
  });

  it('falls back to a safe message for an error carrying no explanation', async () => {
    fetchMock.mockRejectedValue(new TypeError('NetworkError when attempting to fetch'));
    const { result } = renderHook(() => useDocumentSession(vi.fn()));

    await act(async () => {
      await result.current.submit(file());
    });

    // A raw transport message would leak implementation detail and mean nothing
    // to the person reading it.
    expect(result.current.error).toBe('Something went wrong. Please try again.');
  });

  it('returns to idle and clears everything on reset', async () => {
    happyPath();
    const { result } = renderHook(() => useDocumentSession(vi.fn()));

    await act(async () => {
      await result.current.submit(file());
    });
    await act(async () => {
      await result.current.reset();
    });

    expect(result.current.phase).toBe('idle');
    expect(result.current.summary).toBeNull();
    expect(result.current.analysis).toBeNull();
  });
});
