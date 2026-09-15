import { useCallback, useId, useRef, useState } from 'react';

import { Icon } from '@/components/Icon';
import { StatusMessage } from '@/components/StatusMessage';
import type { SessionPhase } from '@/hooks/useDocumentSession';

interface UploadPanelProps {
  readonly phase: SessionPhase;
  readonly error: string | null;
  readonly onSubmit: (file: File) => void;
}

const ACCEPTED = '.pdf,.docx,.txt,application/pdf,text/plain';
const MAX_MEGABYTES = 10;

/**
 * The upload surface.
 *
 * Drag-and-drop is an enhancement layered over a real `<input type="file">`:
 * the input is the accessible control that keyboard and screen-reader users
 * operate through its `<label>`, and the drop zone only adds a pointer
 * affordance. The input is visually hidden rather than `display: none`, because
 * a hidden-by-display input is removed from the accessibility tree entirely.
 */
export function UploadPanel({
  phase,
  error,
  onSubmit,
}: UploadPanelProps): React.ReactElement {
  const inputId = useId();
  const describedById = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const busy = phase === 'uploading' || phase === 'analysing';

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file) onSubmit(file);
    },
    [onSubmit],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsDragging(false);
      if (!busy) handleFiles(event.dataTransfer.files);
    },
    [busy, handleFiles],
  );

  return (
    <section className="panel" aria-labelledby="upload-heading">
      <div className="panel__header">
        <h2 id="upload-heading">Upload a document</h2>
      </div>

      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions --
          The drop target is a pointer-only enhancement; the labelled file input
          inside it remains the keyboard-operable control. */}
      <div
        className={`dropzone${isDragging ? ' dropzone--active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          if (!busy) setIsDragging(true);
        }}
        onDragLeave={() => {
          setIsDragging(false);
        }}
        onDrop={handleDrop}
      >
        <Icon name="upload" size={32} />

        <input
          ref={inputRef}
          id={inputId}
          className="file-input"
          type="file"
          accept={ACCEPTED}
          disabled={busy}
          aria-describedby={describedById}
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = '';
          }}
        />
        <label className="button button--primary" htmlFor={inputId}>
          Choose a document
        </label>

        <p className="dropzone__formats" id={describedById}>
          PDF, Word (.docx) or plain text, up to {MAX_MEGABYTES} MB. You can also drag a
          file onto this area. Your document is held in memory for 30 minutes and is never
          written to disk.
        </p>
      </div>

      {phase === 'uploading' && (
        <StatusMessage tone="info" busy>
          Uploading and indexing your document.
        </StatusMessage>
      )}
      {phase === 'analysing' && (
        <StatusMessage tone="info" busy>
          Reading the document and checking every clause against its own text. This
          usually takes 10 to 30 seconds.
        </StatusMessage>
      )}
      {error !== null && <StatusMessage tone="error">{error}</StatusMessage>}
    </section>
  );
}
