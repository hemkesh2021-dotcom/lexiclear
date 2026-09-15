/** Shapes returned by the LexiClear API, mirroring the backend Pydantic models. */

export type RiskLevel = 'high' | 'medium' | 'low' | 'informational';

export type ClauseCategory =
  | 'payment'
  | 'termination'
  | 'auto_renewal'
  | 'liability'
  | 'indemnity'
  | 'confidentiality'
  | 'intellectual_property'
  | 'data_privacy'
  | 'dispute_resolution'
  | 'restrictive_covenant'
  | 'obligation'
  | 'other';

export interface SourceSpan {
  readonly start: number;
  readonly end: number;
}

export interface ClauseFinding {
  readonly title: string;
  readonly category: ClauseCategory;
  readonly risk: RiskLevel;
  readonly plain_language: string;
  readonly why_it_matters: string;
  readonly quote: string;
  readonly source: SourceSpan | null;
}

export interface ObligationItem {
  readonly who: string;
  readonly what: string;
  readonly when: string;
}

export interface DocumentAnalysis {
  readonly document_id: string;
  readonly document_type: string;
  readonly parties: readonly string[];
  readonly plain_language_summary: string;
  readonly key_dates: readonly string[];
  readonly findings: readonly ClauseFinding[];
  readonly obligations: readonly ObligationItem[];
  readonly questions_for_a_lawyer: readonly string[];
  readonly unverified_finding_count: number;
  readonly disclaimer: string;
}

export interface DocumentSummary {
  readonly document_id: string;
  readonly filename: string;
  readonly character_count: number;
  readonly page_count: number;
  readonly chunk_count: number;
  readonly truncated: boolean;
  readonly expires_in_seconds: number;
}

export interface Citation {
  readonly label: string;
  readonly quote: string;
  readonly start: number;
  readonly end: number;
  readonly score: number;
}

/** A single exchange in the question-and-answer transcript. */
export interface Exchange {
  readonly id: string;
  readonly question: string;
  readonly answer: string;
  readonly citations: readonly Citation[];
  readonly status: 'streaming' | 'complete' | 'error';
  readonly error?: string;
}

/** The error envelope every failing endpoint returns. */
export interface ApiErrorBody {
  readonly code: string;
  readonly message: string;
}
