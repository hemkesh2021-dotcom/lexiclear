# Architecture

This document records the decisions that shaped LexiClear, the reasoning behind
each, and what was rejected. Where a decision has a cost, the cost is stated.

---

## 1. Grounding is enforced by the pipeline, not requested from the model

**Decision.** Every clause finding must carry a verbatim quotation. Each
quotation is located in the source text before the finding is returned. A
finding whose quote cannot be found is discarded and counted.

**Why.** Prompting a model to "only use the document" reduces fabrication; it
does not eliminate it. In a legal tool, a fabricated clause is not a rough edge
— it is the failure that makes the whole category untrustworthy, because the
user has no way to tell a real clause from an invented one. Verification moves
the guarantee from the model's behaviour, which is probabilistic, to the
pipeline's, which is not.

**How.** `services/clause_analysis.py` normalises both the document and the
claimed quote — collapsing whitespace, folding smart quotes, case-insensitively
— then searches. Normalisation is tolerant of the reflowing that PDF extraction
introduces, and intolerant of paraphrase: the words must be present, in order.
The offset map built during normalisation translates a match back to the
original text, and the returned quote is sliced from the document itself, so the
displayed text and the highlight range cannot disagree.

**Cost.** A correct finding whose quote the model paraphrases is lost. That is
the right trade: a missing finding is a gap the user can still investigate, a
fabricated one is a gap they cannot see.

**Rejected.** Asking the model to return character offsets directly. Models
cannot count characters reliably, and an unverifiable offset is worse than no
offset — it looks authoritative and is not.

---

## 2. Hybrid retrieval, fused on normalised scores rather than ranks

**Decision.** BM25 and dense cosine similarity run in parallel; results are
combined by weighted min-max score fusion at 0.6 lexical / 0.4 semantic.

**Why hybrid.** Legal questions split cleanly into two kinds. *"What is the
notice period?"* is semantic — the contract may say "terminate upon thirty (30)
days' written intimation" and never use the word *notice*. *"What does clause
14.2 say?"* is lexical — only an exact match will do. Dense retrieval handles
the first and misses the second; sparse retrieval the reverse.

**Why not Reciprocal Rank Fusion.** RRF is the standard choice, and it was the
first implementation. It is wrong here. RRF deliberately discards score
magnitude, which is correct when ranking millions of documents whose scores are
incomparable. This corpus is a few dozen passages from *one* document, where
magnitude is the dominant signal: a query naming an operative term scores its
clause three to fifty times higher than anything else, while every other passage
sits near zero. Flattening that gap to `1/(k+rank)` let an incidental semantic
match outrank a decisive lexical one — measurably, on the sample contract, for
the arbitration and indemnity queries. Min-max normalisation keeps each
modality's own shape while making the two comparable.

**Why lexical carries more weight.** In legal drafting the operative words are
chosen deliberately. A passage that literally contains "indemnify" is more
likely to be the indemnity clause than one that merely resembles it.

**Why BM25 is implemented here rather than imported.** The corpus is one
document, the algorithm is forty lines, and owning it keeps the image small and
every parameter under test.

---

## 3. Chunking follows clause boundaries

**Decision.** The document is split on clause headings first, then packed to a
character budget, then split on sentence boundaries only if a single clause
overflows. Bare heading lines are folded into the clause beneath them.

**Why.** Fixed-width splitting cuts through the middle of clauses, which
produces citations that begin mid-sentence and answers that miss the operative
verb. Clause boundaries are also what users cite: an answer that says
*"[Clause 4.2]"* can be checked against the paper contract in seconds.

**Invariant.** Every chunk records offsets satisfying
`text[chunk.start:chunk.end] == chunk.text`. This is asserted for every chunk of
the sample contract in `test_chunking.py`. An early implementation violated it
when splitting oversized clauses, which would have put citation highlights on
the wrong passage; the splitter now returns offsets and the caller slices the
source.

---

## 4. Documents live in memory, for thirty minutes, and never touch disk

**Decision.** `DocumentStore` is a bounded LRU with TTL, guarded by an
`asyncio.Lock`. Nothing is written to disk or to a database. The container's
filesystem is read-only.

**Why.** LexiClear handles documents that may be privileged, commercially
sensitive, or both. For a tool of this kind the strongest available control is
not encryption at rest — it is having nothing at rest. An abandoned session
leaves nothing behind, a container restart wipes every trace, and a compromise
of the host yields at most the documents currently being analysed.

**Cost.** A user cannot return tomorrow to a document analysed today, and the
service cannot be scaled by adding workers without either session affinity or a
shared store. Both are stated in the interface and in `docs/DEPLOYMENT.md`. The
store sits behind a narrow interface so that substituting a shared cache is a
contained change.

---

## 5. Untrusted text is contained; untrusted instructions are refused

Two distinct defences, because there are two distinct threats.

**Documents** are attacker-supplied content the user asked us to read. They
cannot be rejected on suspicion — a contract may legitimately quote an
instruction. They are therefore *contained*: wrapped in labelled delimiters,
with any forged delimiter in the text neutralised first, and with a system
instruction stating that everything inside is data and that instruction-like
text is a finding to report, not a directive to follow.

**Questions** are typed by the user. A legitimate question about a contract
never needs to redefine the assistant's role, so override phrasing is rejected
outright, before any model call. The patterns are deliberately narrow — the test
suite asserts that six realistic legal questions pass while eight override
attempts are refused — because a guard that blocks real questions is worse than
no guard.

Neither defence is claimed to be complete. Prompt injection is not a solved
problem, and `SECURITY.md` says so.

---

## 6. One protocol, two providers

`llm/base.py` declares a `Protocol` with three methods. `gemini.py` implements
it against the Gemini API; `mock.py` implements it deterministically in-process.
Everything else depends on the protocol.

**Why it matters beyond testability.** The mock is not a stub that returns
fixed strings. Its embeddings are hashed bag-of-words vectors, so texts sharing
vocabulary land near each other and retrieval tests assert real ranking
behaviour. Its JSON generation is schema-driven, and quote fields are filled
with actual sentences lifted from the document in the prompt — which means the
verification stage is genuinely exercised. Flipping `fabricate_quotes=True`
makes it emit text absent from the document, which is how the discard path is
tested.

The result: CI runs the entire product — upload, chunking, embedding, retrieval,
analysis, verification, streaming — on every push, with no API key, no network
call, and no flakiness from model sampling. The end-to-end suite runs the same
way against the production container.

---

## 7. Structured output over prose parsing

Analysis uses Gemini's structured-output mode with a JSON Schema derived from
the Pydantic model that also validates the response, via
`prompts.json_schema_for`. The schema the model is constrained to and the schema
the API validates against therefore cannot drift apart.

The converter inlines `$ref` pointers, collapses `anyOf` unions containing
`null` into a nullable member, and drops keywords the decoder does not accept —
with a test that walks the converted schema and asserts no unsupported keyword
survives.

---

## 8. Streaming answers over server-sent events

A grounded legal answer runs to several sentences. Buffering it turns a
six-second generation into a six-second blank screen; streaming turns it into a
response that starts in under a second.

Citations are resolved *before* generation begins and sent as the first event,
so the interface can render the passages the answer will draw on while the prose
is still arriving. That ordering also means a user who only wanted to find the
relevant clause has it immediately.

SSE rather than WebSocket: the exchange is one-directional, SSE crosses proxies
without special configuration, and there is no connection state to manage.

`EventSource` cannot issue a POST, so the client reads the stream from `fetch`
and frames it manually — splitting on the blank-line delimiter and carrying any
partial tail into the next chunk, which is what stops a token straddling a
network boundary from being dropped. There is a test for exactly that.

---

## 9. Expensive work happens once per document, not once per request

Model calls dominate both latency and cost, so the pipeline is arranged to make
as few of them as possible:

- **Content addressing.** Each document carries a SHA-256 of its normalised
  text. Re-uploading content that is still held (the web client does this by
  itself when a session expires) reuses the chunks, embedding index and
  analysis: zero embedding calls, zero analysis calls. Each upload still gets
  its own handle, and reused results are rebound to it.
- **Single-flight analysis.** A per-document lock means five concurrent
  analysis requests produce one model call, not five.
- **Off-loop parsing.** PDF/DOCX extraction and chunking are CPU-bound and run
  in a worker thread, so a large upload never stalls other users' streams.
- **Bounded fan-out.** Embedding batches run concurrently, capped by
  `embedding_max_concurrency`, so one long document cannot exhaust the quota.
- **Index built once, as an inverted index.** Each term's BM25 weight in each
  chunk is precomputed at upload. Scoring a question is one vectorised addition
  per query term over only the chunks that contain it, plus one matrix-vector
  product for the semantic side; ranking uses `np.lexsort`, not a Python sort.
- **Bounded extraction.** PDF pages past the retention ceiling are never parsed:
  a 500-page upload costs what its first few pages cost.
- **Constant-time bookkeeping.** Content lookups go through a hash index, and
  TTL expiry pops from a creation-ordered queue instead of scanning the store.
- **Memoised transcript.** Each chat exchange is a memoised component, so a
  streamed token re-renders one list item rather than the whole conversation.
- **Cache-friendly delivery.** Fingerprinted assets are served
  `immutable` for a year and compressed with gzip; only the HTML shell is
  revalidated, so repeat visits download nothing but the shell.

---

## 10. Single origin

The container serves the API and the built web client from one process. This is
not packaging convenience: it is what allows `default-src 'self'` with no
cross-origin exceptions, and removes CORS from the production path entirely. The
Vite dev server proxies `/api` for the same reason, so the policy is identical
in development and production rather than being loosened for local work.

---

## 11. Accessibility is a build gate, not a review step

`eslint-plugin-jsx-a11y` runs in **strict** mode with violations as errors.
axe-core runs in the unit suite via a typed helper, and again in Playwright
across both colour schemes, at 320 CSS pixels and at 200% zoom — the rules that
need layout and painting, such as colour contrast, can only be evaluated in a
real browser.

The design pays for this. Neumorphic soft-shadow surfaces are the intended
visual direction, but shadow alone fails for anyone who cannot resolve
low-contrast edges and disappears entirely in Windows High Contrast mode. Every
raised surface therefore carries both a shadow *and* a one-pixel border, and a
`forced-colors` block replaces shadows with borders outright. Risk level is
conveyed by a word, a border position and a colour, never colour alone.

[`docs/ACCESSIBILITY.md`](ACCESSIBILITY.md) maps each WCAG criterion to where it
is implemented and where it is tested.
