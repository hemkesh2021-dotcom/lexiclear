# LexiClear

**Understand a legal document before you sign it.**

LexiClear reads a contract, policy or notice you upload, explains it in plain
language, flags the clauses that deserve your attention, and answers questions
about it — using only your document, with citations.

It provides information, not legal advice.

> **Live demo:** _<add your deployed URL here>_
> **Problem statement:** AI for Legal Assistance & Access — PromptWars: Virtual

---

## The problem this addresses

A person handed a rental agreement, an employment contract or an insurance
policy faces a document written by someone else's lawyer, for someone else's
benefit, in language designed to be precise rather than clear. Most people sign
it anyway, because the alternative — paying for an hour of legal time to read
four pages — costs more than the decision feels worth.

The gap is not legal *advice*. It is legal *comprehension*: knowing what a
document actually says, which parts are unusual, what it obliges you to do, and
which specific questions are worth paying a professional to answer.

That is the gap LexiClear closes.

## What it does

Upload a PDF, Word document or text file, and LexiClear returns:

| Output | What it gives you |
| --- | --- |
| **Plain-language summary** | The document explained at secondary-school reading level, with every term of art expanded. |
| **Clauses to read closely** | Each significant clause with its plain meaning, why it matters to you, and the document's own wording as evidence. Ranked by how much attention a non-lawyer should give it. |
| **Obligations checklist** | Who must do what, and by when. |
| **Questions for a lawyer** | Specific, document-grounded questions worth paying a professional to answer — which is far cheaper than paying one to read the whole thing. |
| **Grounded question answering** | Ask anything about the document. Answers are built only from passages retrieved from it, cited by clause, streamed as they are written. |

### Coverage of the problem statement

| Suggested use case | How LexiClear addresses it |
| --- | --- |
| Simplifying complex legal documents | Plain-language summary plus per-clause explanations, every one anchored to a verbatim quotation. |
| Highlighting important clauses, obligations, risks | Clause findings categorised across twelve clause types and four attention levels, ordered so the clauses that matter come first. |
| Answering questions based on provided legal documents | Hybrid retrieval over the document's own passages, with clause-level citations and an explicit refusal when the document does not say. |
| Helping users understand options and next steps | The "questions for a lawyer" output turns a vague worry into a specific, priced conversation. |
| Generating summaries, checklists, actionable outputs | Obligations checklist with party, action and deadline. |
| Helping users prepare for a legal professional | The same output, designed as the brief you take to that appointment. |

### The design decision that matters most

**Every finding is verified against the document before you see it.**

The model is asked to quote the document verbatim for each clause it reports.
Each quotation is then located in the source text. A finding whose quote cannot
be found is *discarded*, and the response reports how many were dropped
(`unverified_finding_count`). The quote you read is the document's own bytes,
sliced at the verified offsets — not the model's rendering of them.

This is the difference between a tool that is usually right about a contract and
one you can act on. A hallucinated clause in a legal summary is not a cosmetic
defect; it is the failure mode that makes the whole category untrustworthy.
The behaviour is enforced by tests that feed the pipeline deliberately
fabricated quotes and assert that nothing survives
([`test_clause_analysis.py`](backend/tests/unit/test_clause_analysis.py)).

---

## Architecture

```
Browser (React 19 · TypeScript · WCAG 2.1 AA)
   │  single origin — no CORS in production, CSP stays at default-src 'self'
   ▼
FastAPI  ── security headers · per-address rate limits · typed error envelope
   │
   ├── Ingestion ──▶ magic-byte validation ▶ extraction ▶ clause-aware chunking
   │                 ▶ Gemini embeddings ▶ in-memory index (TTL, never on disk)
   │
   ├── Analysis  ──▶ Gemini 2.5 Flash, structured output
   │                 ▶ quote verification against source ▶ unverifiable dropped
   │
   └── Q&A       ──▶ BM25 + dense hybrid retrieval ▶ Gemini streaming ▶ SSE
```

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) explains each decision and what
was rejected. [`SECURITY.md`](SECURITY.md) sets out the threat model.

### Google AI services used

| Service | Model | Where |
| --- | --- | --- |
| **Gemini API** — text generation, structured output | `gemini-2.5-flash` | Clause analysis, summarisation, obligation extraction. JSON Schema is enforced by the decoder, not by parsing prose afterwards. |
| **Gemini API** — text generation, streaming | `gemini-2.5-flash` | Grounded question answering, streamed over server-sent events. |
| **Gemini API** — embeddings | `gemini-embedding-001` @ 768 dimensions | Passage and query embeddings for semantic retrieval, using asymmetric `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` task types. |

All access goes through the official `google-genai` SDK, confined to
[`backend/app/llm/gemini.py`](backend/app/llm/gemini.py) behind a `Protocol`
([`llm/base.py`](backend/app/llm/base.py)). Every other module depends on the
protocol, which is what lets the entire pipeline run in CI against a
deterministic stand-in with no API key and no network call.

---

## Running it

### Quick start

```bash
git clone <your-repo-url> && cd lexiclear
cp .env.example .env          # add your key from https://aistudio.google.com/apikey
make install
make dev                      # API on :8000, web client on :5173
```

### Without an API key

The mock provider runs the whole product offline — upload, analysis, retrieval,
streaming answers — with deterministic stand-in outputs:

```bash
LEXICLEAR_LLM_PROVIDER=mock make dev
```

### Container

```bash
make run                      # builds and serves on http://localhost:8000
```

Deployment to Hugging Face Spaces or Vercel: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## Quality

Run everything CI runs, locally, with `make check`.

| Gate | Status |
| --- | --- |
| Backend tests | **194 tests**, 96% coverage (gate: 90%) |
| Frontend tests | **73 tests**, 96% statement coverage (gate: 90%) |
| End-to-end | **26 tests**, real browser, desktop and mobile viewports, against the production image |
| Accessibility | axe-core WCAG 2.1 AA in unit *and* browser suites, light and dark, 320 px and 200% zoom |
| Types | `mypy --strict` and `tsc --strict` with `noUncheckedIndexedAccess`, zero errors, zero `Any` escapes |
| Lint | `ruff` (17 rule families incl. `S` security, `ANN`, `D`) and `eslint` with `jsx-a11y` **strict** as errors |
| Security | `bandit`, `pip-audit --strict`, `npm audit`, CodeQL `security-and-quality`, committed-secret check — **zero known vulnerabilities** |

### What the tests actually caught

These are defects the suite found during development, not hypotheticals:

- **Chunk offsets drifted from chunk text** when an oversized clause was split,
  so a citation highlight would have pointed at the wrong passage. Fixed by
  making the splitter return offsets and slice the source, with an invariant
  test asserting `text[chunk.start:chunk.end] == chunk.text` for every chunk.
- **A 16-digit card number was only partly redacted**, because the 12-digit
  Aadhaar pattern matched first and left four digits in the clear. Fixed by
  ordering the patterns longest-first, with a test per identifier class.
- **Reciprocal Rank Fusion was the wrong fusion for this corpus.** RRF discards
  score magnitude, which is the dominant signal when there are forty passages
  rather than forty million — so an incidental semantic match outranked a
  decisive lexical one. Replaced with weighted min-max score fusion; the
  retrieval tests assert that a query about the arbitration clause returns the
  arbitration clause.
- **Keyboard focus was lost after every question**, because focus was restored
  while the field was still disabled. Fixed with an effect that waits for the
  re-enabling render.
- **Route settings came from the global singleton, not the instance**, so
  per-instance configuration was silently ignored.
- **An unknown `/api/...` path returned the web client with `200 OK`**, because
  the single-page-app fallback swallowed it. An API client reads that as
  success and an uptime monitor reads it as healthy. It now returns a JSON 404.

---

## Repository layout

```
backend/
  app/
    api/v1/        HTTP routes — thin adapters, no pipeline logic
    core/          config · logging · typed errors · transport security
    llm/           base.py (Protocol) · gemini.py · mock.py · factory.py
    schemas/       Pydantic request and response models
    security/      file validation · prompt containment · PII redaction
    services/      ingestion · extraction · chunking · retrieval · analysis · Q&A
  tests/           unit + integration, 194 tests
frontend/
  src/             React 19 + TypeScript, strict
  e2e/             Playwright journey + WCAG audit
docs/              ARCHITECTURE · DEPLOYMENT · ACCESSIBILITY · DEMO_SCRIPT
samples/           A sample rental agreement to try it with
```

## Limitations

Stated plainly, because a tool in this space that oversells itself is worse than
no tool:

- **It is not legal advice.** It explains what a document says. It does not tell
  you whether to sign, predict how a court would rule, or assess your position
  in a dispute.
- **Scanned documents are refused, not guessed at.** An image-only PDF yields no
  text, and the app says so rather than returning an empty analysis. OCR is a
  clear next step.
- **One document at a time.** Contract-to-contract comparison is the obvious
  extension; the retrieval layer already supports it, the product surface does
  not yet.
- **Long documents are truncated** at 400,000 characters, and the response says
  when that has happened.
- **Jurisdiction-agnostic.** It reads what the document says; it does not know
  which local statute might override a clause.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
