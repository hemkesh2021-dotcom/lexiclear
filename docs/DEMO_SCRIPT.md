# Demo video script

Target: **under 4 minutes**, screen recording with voice-over. The submission
guidance asks for a walkthrough covering UI/UX, live testing, and an explicit
statement of which GenAI services are used and where.

Record at 1920×1080. Zoom the browser to 110% so text is legible after
compression. Have `samples/sample-rental-agreement.txt` ready, plus one real PDF.

---

## 0:00 – 0:25 — The problem, not the product

> "This is a rental agreement. Eleven months, four pages, written by the
> landlord's lawyer. Clause 4.1 lets the landlord end it with fifteen days
> notice. Clause 4.2 says I need to give three months — and if I don't, I lose
> the entire deposit. Most people sign this without noticing, because the
> alternative is paying a lawyer more than the decision feels worth."

Scroll the document on screen while speaking. Do not show the app yet.

---

## 0:25 – 0:50 — Upload

> "LexiClear reads it instead."

Drag the file in. While it processes:

> "The document is validated by its actual contents, not its file extension,
> then split along clause boundaries and indexed. It's held in memory for thirty
> minutes and never written to disk."

---

## 0:50 – 1:40 — The analysis

Let the results land. Scroll slowly.

> "A plain-language summary. Then the clauses that deserve attention, ordered by
> how much attention they deserve."

Stop on the fifteen-day termination finding.

> "What it means, why it matters, and — this is the part that counts — the
> contract's own words underneath. Every finding has to quote the document
> verbatim. The system then goes back and checks that the quote is actually
> there. If it isn't, the finding is thrown away and the count is shown to you."

Point at `unverified_finding_count` if it is non-zero.

> "A legal tool that invents a clause is worse than no tool, because you can't
> tell which one it invented."

Scroll to the obligations checklist and the lawyer questions.

> "What I have to do and by when. And the specific questions worth paying a
> lawyer to answer — which costs a great deal less than paying one to read the
> whole thing."

---

## 1:40 – 2:20 — Live question answering

> "And I can ask it anything."

Type: **"What happens if I terminate early?"**

> "Answers come only from passages retrieved from this document. Watch the
> citations arrive first — those are the clauses the answer is built from, so I
> can check it against the paper before the answer has finished writing."

Expand the citations panel. Then:

> "Ask it something the contract doesn't cover, and it says so rather than
> guessing."

Ask: **"Can I sublet the flat?"** (the sample does not address subletting).

---

## 2:20 – 2:45 — Accessibility

> "Everything works from the keyboard."

Tab from the top: skip link, file input, controls. Then toggle dark mode.

> "Risk is stated in words, not just colour. Both themes are audited against
> WCAG 2.1 AA by axe-core in a real browser on every push — including contrast,
> reflow at three hundred and twenty pixels, and two hundred per cent zoom."

Shrink the window to phone width to show the reflow.

---

## 2:45 – 3:20 — GenAI architecture

Show `docs/ARCHITECTURE.md` or a diagram.

> "Three Google AI services. Gemini 3.6 Flash in structured-output mode for the
> clause analysis — the JSON schema is enforced by the decoder, not by parsing
> prose afterwards. Gemini 3.6 Flash again, streaming, for the answers.
> And gemini-embedding-001 at seven hundred and sixty-eight dimensions for
> semantic retrieval, using separate task types for passages and queries."

> "Retrieval is hybrid: BM25 for the exact legal terminology, embeddings for the
> cases where the contract words a concept differently from the question, fused
> on normalised scores."

> "All of it sits behind one protocol, so the whole pipeline runs in CI against
> a deterministic stand-in — no API key, no network call, no flaky tests."

---

## 3:20 – 3:45 — Engineering

Show the CI run, green.

> "Two hundred and ninety-three tests. Ninety-six per cent backend coverage,
> ninety-six per cent frontend. Strict type checking on both sides.
> Bandit, pip-audit, npm audit and CodeQL. End-to-end tests against the
> production container image."

> "The suite earned its keep: it caught a chunk-offset bug that would have put
> citation highlights on the wrong passage, a redaction bug that left four
> digits of a card number in the clear, and a retrieval fusion that was ranking
> the wrong clause first."

---

## 3:45 – 4:00 — Close

> "LexiClear tells you what your document says. It doesn't tell you what to do —
> that's still a lawyer's job. It just makes that conversation a lot shorter,
> and a lot cheaper."

---

## Checklist before recording

- [ ] `LEXICLEAR_ENVIRONMENT=production` and a working API key
- [ ] Browser cleared of extensions that inject UI
- [ ] Deployed URL visible in the address bar, not `localhost`
- [ ] A second, real PDF ready in case the first upload misbehaves
- [ ] Gemini named out loud at least twice
- [ ] Not-legal-advice boundary stated at least once
