import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '@/test/a11y';
import { AnalysisPanel } from '@/components/AnalysisPanel';
import { analysisFixture, summaryFixture } from '@/test/fixtures';

function renderPanel(overrides = {}) {
  const onClear = vi.fn();
  const result = render(
    <main>
      <AnalysisPanel
        analysis={{ ...analysisFixture, ...overrides }}
        summary={summaryFixture}
        onClear={onClear}
      />
    </main>,
  );
  return { ...result, onClear };
}

describe('AnalysisPanel', () => {
  it('shows the document type as the section heading', () => {
    renderPanel();
    expect(
      screen.getByRole('heading', { name: 'Residential rental agreement' }),
    ).toBeInTheDocument();
  });

  it('renders every finding with its plain-language explanation', () => {
    renderPanel();
    for (const finding of analysisFixture.findings) {
      expect(screen.getByRole('heading', { name: finding.title })).toBeInTheDocument();
      expect(screen.getByText(finding.plain_language)).toBeInTheDocument();
    }
  });

  it('quotes the document verbatim beneath each finding', () => {
    renderPanel();
    const quotes = screen.getAllByText(/The Landlord may terminate this Agreement/);
    expect(quotes.length).toBeGreaterThan(0);
  });

  it('states risk in words, not only in colour', () => {
    renderPanel();
    expect(screen.getByText('Read closely')).toBeInTheDocument();
    expect(screen.getByText('Worth checking')).toBeInTheDocument();
  });

  it('lists obligations with who, what and when', () => {
    renderPanel();
    const section = screen
      .getByRole('heading', { name: /What this document requires/ })
      .closest('section');
    expect(section).not.toBeNull();
    expect(within(section!).getAllByText('Tenant')).toHaveLength(2);
    expect(screen.getByText('Pay rent of INR 45,000')).toBeInTheDocument();
    expect(screen.getByText('When: By the 5th of each month')).toBeInTheDocument();
  });

  it('surfaces the questions to put to a lawyer', () => {
    renderPanel();
    const section = screen
      .getByRole('heading', { name: /Questions to put to a lawyer/ })
      .closest('section');
    expect(section).not.toBeNull();
    expect(
      within(section!).getByText(/Is a 15-day landlord termination right enforceable/),
    ).toBeInTheDocument();
  });

  it('discloses how many findings were discarded as unverifiable', () => {
    renderPanel();
    expect(screen.getByText(/1 additional/)).toBeInTheDocument();
    expect(screen.getByText(/could not be matched to wording/)).toBeInTheDocument();
  });

  it('says nothing about discarded findings when there were none', () => {
    renderPanel({ unverified_finding_count: 0 });
    expect(screen.queryByText(/could not be matched to wording/)).not.toBeInTheDocument();
  });

  it('warns when the document was too long to analyse in full', () => {
    render(
      <main>
        <AnalysisPanel
          analysis={analysisFixture}
          summary={{ ...summaryFixture, truncated: true }}
          onClear={vi.fn()}
        />
      </main>,
    );
    expect(screen.getByText(/longer than the size we analyse/)).toBeInTheDocument();
  });

  it('always shows the not-legal-advice notice', () => {
    renderPanel();
    const notice = screen.getByRole('complementary', { name: 'Important notice' });
    expect(notice).toHaveTextContent('This is information, not legal advice.');
  });

  it('explains that no clause could be verified when the list is empty', () => {
    renderPanel({ findings: [] });
    expect(screen.getByText(/No clauses could be verified/)).toBeInTheDocument();
  });

  it('clears the document when asked', async () => {
    const user = userEvent.setup();
    const { onClear } = renderPanel();
    await user.click(screen.getByRole('button', { name: /Clear document/ }));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it('has no detectable accessibility violations', async () => {
    const { container } = renderPanel();
    await expectNoAxeViolations(container);
  });
});
