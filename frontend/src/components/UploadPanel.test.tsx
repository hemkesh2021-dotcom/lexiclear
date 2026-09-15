import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '@/test/a11y';
import { UploadPanel } from '@/components/UploadPanel';

function renderPanel(props: Partial<React.ComponentProps<typeof UploadPanel>> = {}) {
  const onSubmit = vi.fn();
  const result = render(
    <main>
      <UploadPanel phase="idle" error={null} onSubmit={onSubmit} {...props} />
    </main>,
  );
  return { ...result, onSubmit };
}

const contract = () =>
  new File(['RESIDENTIAL RENTAL AGREEMENT'], 'lease.txt', { type: 'text/plain' });

describe('UploadPanel', () => {
  it('exposes a labelled file input, not a div pretending to be one', () => {
    renderPanel();
    const input = screen.getByLabelText(/Choose a document/);
    expect(input).toHaveAttribute('type', 'file');
  });

  it('describes the accepted formats and the retention policy to assistive tech', () => {
    renderPanel();
    const input = screen.getByLabelText(/Choose a document/);
    const description = document.getElementById(input.getAttribute('aria-describedby') ?? '');
    expect(description).toHaveTextContent(/PDF, Word/);
    expect(description).toHaveTextContent(/never written to disk/);
  });

  it('submits the chosen file', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderPanel();
    await user.upload(screen.getByLabelText(/Choose a document/), contract());
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit.mock.calls[0]?.[0]).toBeInstanceOf(File);
  });

  it('can be operated entirely from the keyboard', async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.tab();
    expect(screen.getByLabelText(/Choose a document/)).toHaveFocus();
  });

  it('disables the input while a document is being processed', () => {
    renderPanel({ phase: 'analysing' });
    expect(screen.getByLabelText(/Choose a document/)).toBeDisabled();
  });

  it('announces upload progress through a status role', () => {
    renderPanel({ phase: 'uploading' });
    expect(screen.getByRole('status')).toHaveTextContent(/Uploading and indexing/);
  });

  it('announces analysis progress and sets an expectation of how long it takes', () => {
    renderPanel({ phase: 'analysing' });
    expect(screen.getByRole('status')).toHaveTextContent(/10 to 30 seconds/);
  });

  it('reports an error through an alert role so it interrupts', () => {
    renderPanel({ phase: 'error', error: 'Documents must be smaller than 10 MB.' });
    expect(screen.getByRole('alert')).toHaveTextContent('Documents must be smaller than 10 MB.');
  });

  it('accepts a dropped file', () => {
    const { onSubmit, container } = renderPanel();
    const zone = container.querySelector('.dropzone');
    expect(zone).not.toBeNull();

    fireEvent.drop(zone!, { dataTransfer: { files: [contract()] } });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('ignores a drop while a document is already being processed', () => {
    const { onSubmit, container } = renderPanel({ phase: 'uploading' });
    fireEvent.drop(container.querySelector('.dropzone')!, {
      dataTransfer: { files: [contract()] },
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('highlights the drop zone while a file is dragged over it', () => {
    const { container } = renderPanel();
    const zone = container.querySelector('.dropzone');
    expect(zone).not.toBeNull();

    fireEvent.dragOver(zone!, { dataTransfer: { files: [] } });
    expect(zone).toHaveClass('dropzone--active');

    fireEvent.dragLeave(zone!);
    expect(zone).not.toHaveClass('dropzone--active');
  });

  it('does not highlight the drop zone while a document is processing', () => {
    const { container } = renderPanel({ phase: 'analysing' });
    const zone = container.querySelector('.dropzone');
    fireEvent.dragOver(zone!, { dataTransfer: { files: [] } });
    expect(zone).not.toHaveClass('dropzone--active');
  });

  it('has no detectable accessibility violations', async () => {
    const { container } = renderPanel();
    await expectNoAxeViolations(container);
  });
});
