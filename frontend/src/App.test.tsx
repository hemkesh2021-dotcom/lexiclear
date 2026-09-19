import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '@/test/a11y';
import { App } from '@/App';
import {
  analysisFixture,
  citationsFixture,
  frame,
  sseResponse,
  summaryFixture,
} from '@/test/fixtures';

const fetchMock = vi.fn();

/** Route each call to the response the real API would return. */
function routeApi(): void {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (url === '/api/v1/documents' && init?.method === 'POST') {
      return Promise.resolve(new Response(JSON.stringify(summaryFixture), { status: 201 }));
    }
    if (url.endsWith('/analysis')) {
      return Promise.resolve(new Response(JSON.stringify(analysisFixture), { status: 200 }));
    }
    if (url.endsWith('/questions')) {
      return Promise.resolve(
        sseResponse([
          frame('citations', { citations: citationsFixture }),
          frame('token', { text: 'Three months notice [Clause 4.2].' }),
          frame('done', { disclaimer: 'Not legal advice.' }),
        ]),
      );
    }
    return Promise.resolve(new Response(null, { status: 204 }));
  });
}

const contract = () =>
  new File(['RESIDENTIAL RENTAL AGREEMENT'], 'rental-agreement.txt', { type: 'text/plain' });

async function uploadAndWait(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(screen.getByLabelText(/Choose a document/), contract());
  await waitFor(() => {
    expect(
      screen.getByRole('heading', { name: 'Residential rental agreement' }),
    ).toBeInTheDocument();
  });
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    routeApi();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('presents the landmarks assistive technology navigates by', () => {
    render(<App />);
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });

  it('offers a skip link as the first focusable element', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.tab();
    const skip = screen.getByRole('link', { name: 'Skip to main content' });
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute('href', '#main-content');
  });

  it('has exactly one first-level heading', () => {
    render(<App />);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('states up front that it is not legal advice', () => {
    render(<App />);
    expect(screen.getByRole('contentinfo')).toHaveTextContent(/not legal advice/);
  });

  it('runs the whole journey: upload, analyse, ask, clear', async () => {
    const user = userEvent.setup();
    render(<App />);

    await uploadAndWait(user);
    expect(
      screen.getByRole('heading', { name: /The landlord can end the agreement/ }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /How can this agreement be ended/ }));
    // Scoped to the transcript: the same wording also reaches the live region,
    // which is exactly what the announcement test asserts separately.
    await waitFor(() => {
      expect(within(screen.getByRole('log')).getByText(/Three months notice/)).toBeVisible();
    });

    await user.click(screen.getByRole('button', { name: /Clear document/ }));
    await waitFor(() => {
      expect(screen.getByLabelText(/Choose a document/)).toBeInTheDocument();
    });
  });

  it('deletes the document from the server when cleared', async () => {
    const user = userEvent.setup();
    render(<App />);
    await uploadAndWait(user);
    await user.click(screen.getByRole('button', { name: /Clear document/ }));

    await waitFor(() => {
      const deletes = fetchMock.mock.calls.filter(
        (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
      );
      expect(deletes.length).toBeGreaterThan(0);
    });
  });

  it('announces each stage of the journey through a live region', async () => {
    const user = userEvent.setup();
    render(<App />);
    const status = screen.getByRole('status');

    await user.upload(screen.getByLabelText(/Choose a document/), contract());
    await waitFor(() => {
      expect(status).toHaveTextContent(/Analysis complete/);
    });
    expect(status).toHaveTextContent(/2 clauses to review/);
  });

  it('shows an upload failure without losing the upload control', async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ code: 'file_too_large', message: 'Documents must be smaller.' }),
        { status: 413 },
      ),
    );
    render(<App />);

    await user.upload(screen.getByLabelText(/Choose a document/), contract());
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Documents must be smaller.');
    });
    expect(screen.getByLabelText(/Choose a document/)).toBeEnabled();
  });

  it('offers to retry an analysis that failed after a successful upload', async () => {
    const user = userEvent.setup();
    let analysisCalls = 0;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/v1/documents' && init?.method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify(summaryFixture), { status: 201 }));
      }
      if (url.endsWith('/analysis')) {
        analysisCalls += 1;
        return Promise.resolve(
          analysisCalls === 1
            ? new Response(JSON.stringify({ code: 'llm_unavailable', message: 'Busy.' }), {
                status: 503,
              })
            : new Response(JSON.stringify(analysisFixture), { status: 200 }),
        );
      }
      return Promise.resolve(new Response(null, { status: 204 }));
    });
    render(<App />);

    await user.upload(screen.getByLabelText(/Choose a document/), contract());
    await user.click(await screen.findByRole('button', { name: 'Try the analysis again' }));

    expect(
      await screen.findByRole('heading', { name: 'Residential rental agreement' }),
    ).toBeInTheDocument();
  });

  it('has no detectable accessibility violations before upload', async () => {
    const { container } = render(<App />);
    await expectNoAxeViolations(container);
  });

  it('has no detectable accessibility violations once results are shown', async () => {
    const user = userEvent.setup();
    const { container } = render(<App />);
    await uploadAndWait(user);
    await expectNoAxeViolations(container);
  });
});
