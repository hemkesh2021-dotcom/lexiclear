import type { Citation, DocumentAnalysis, DocumentSummary } from '@/api/types';

/** A realistic analysis fixture, shaped exactly as the API returns one. */
export const analysisFixture: DocumentAnalysis = {
  document_id: 'doc-123',
  document_type: 'Residential rental agreement',
  parties: ['Meridian Properties Private Limited', 'Ms. Anita Raghavan'],
  plain_language_summary:
    'This is an eleven-month rental agreement for a flat in Bengaluru. It sets the rent, ' +
    'the deposit, and how either side can end the arrangement.',
  key_dates: ['Starts 1 May 2026', 'Ends 31 March 2027', '60 days notice before renewal'],
  findings: [
    {
      title: 'The landlord can end the agreement with 15 days notice',
      category: 'termination',
      risk: 'high',
      plain_language:
        'The landlord may end this agreement at any time by giving you fifteen days written notice.',
      why_it_matters:
        'You could be asked to leave with two weeks notice, while you must give three months.',
      quote:
        '4.1 The Landlord may terminate this Agreement at any time by giving the Tenant fifteen (15) days written notice.',
      source: { start: 1848, end: 1990 },
    },
    {
      title: 'Rent rises 10% on every renewal',
      category: 'payment',
      risk: 'medium',
      plain_language: 'Each time the agreement renews, the monthly rent goes up by ten per cent.',
      why_it_matters: 'Over three renewals the rent would rise by roughly a third.',
      quote: '3.2 On each renewal the monthly rent shall increase by ten per cent (10%)',
      source: { start: 1696, end: 1830 },
    },
  ],
  obligations: [
    { who: 'Tenant', what: 'Pay rent of INR 45,000', when: 'By the 5th of each month' },
    { who: 'Tenant', what: 'Give notice before leaving', when: 'Three months in advance' },
  ],
  questions_for_a_lawyer: [
    'Is a 15-day landlord termination right enforceable here?',
    'Can the arbitration clause be challenged if the landlord appoints the arbitrator?',
  ],
  unverified_finding_count: 1,
  disclaimer:
    'LexiClear provides general information to help you understand a document. It is not ' +
    'legal advice and does not create a lawyer-client relationship.',
};

export const summaryFixture: DocumentSummary = {
  document_id: 'doc-123',
  filename: 'rental-agreement.txt',
  character_count: 4225,
  page_count: 1,
  chunk_count: 18,
  truncated: false,
  expires_in_seconds: 1800,
};

export const citationsFixture: readonly Citation[] = [
  {
    label: 'Clause 4.2',
    quote: '4.2 The Tenant may terminate this Agreement only after completion of six (6) months.',
    start: 1992,
    end: 2220,
    score: 0.91,
  },
];

/** Build a `Response` that streams the given server-sent-event frames. */
export function sseResponse(frames: readonly string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

/** Format one server-sent-event frame. */
export function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}
