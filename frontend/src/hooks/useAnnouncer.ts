import { useCallback, useState } from 'react';

/**
 * Drives a polite ARIA live region.
 *
 * Screen readers ignore a live region whose text has not changed, so repeating
 * the same message - "Analysis complete" after two uploads in a row - would be
 * silently dropped. A monotonically increasing nonce is appended in a
 * zero-width span so the text always differs while the visible wording does not.
 */
export interface Announcer {
  readonly message: string;
  readonly nonce: number;
  announce: (message: string) => void;
}

export function useAnnouncer(): Announcer {
  const [state, setState] = useState<{ message: string; nonce: number }>({
    message: '',
    nonce: 0,
  });

  const announce = useCallback((message: string) => {
    setState((previous) => ({ message, nonce: previous.nonce + 1 }));
  }, []);

  return { message: state.message, nonce: state.nonce, announce };
}
