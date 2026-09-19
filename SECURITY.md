# Security

LexiClear accepts arbitrary files from anonymous users, extracts text from them,
and sends that text to a third-party model. Each of those steps is a trust
boundary. This document states what is defended, how, and what is not.

## Reporting a vulnerability

Open a private security advisory on the repository rather than a public issue.

---

## Threat model

| Threat | Control | Where |
| --- | --- | --- |
| Malicious file disguised by extension or `Content-Type` | Format determined from magic bytes; the client's claims are hints only | `security/file_validation.py` |
| Path traversal via filename | Filename NFKC-normalised, separators and control characters stripped, length capped; used only for display | `security/file_validation.py` |
| Resource exhaustion by upload size | Read with a one-byte overshoot and rejected before the body is materialised; 10 MB ceiling | `api/v1/documents.py` |
| Resource exhaustion by document length | Text truncated at 400,000 characters, and the response says so | `services/extraction.py` |
| Resource exhaustion by request volume | Per-address rate limits on all three model-backed endpoints | `core/security.py` |
| Rate-limit evasion by forged `X-Forwarded-For` | Proxy headers trusted only from private-network peers (the platform load balancer), never from `*` | `Dockerfile` (`FORWARDED_ALLOW_IPS`) |
| Handle leakage through reused work | Identical re-uploads reuse embeddings and analysis, but every upload gets a fresh 128-bit handle and reused results are rebound to it | `services/store.py` |
| Memory exhaustion | Bounded LRU store with TTL eviction | `services/store.py` |
| Prompt injection from document content | Labelled delimiters, forged delimiters neutralised, system instruction declares the block to be data | `security/prompt_guard.py` |
| Prompt injection from user questions | Override phrasing refused before any model call | `security/prompt_guard.py` |
| Model fabrication reaching the user | Every finding's quote verified against the source; unverifiable findings discarded and counted | `services/clause_analysis.py` |
| Personal identifiers sent to a third party | Direct identifiers replaced with placeholders before egress, restored on return | `security/redaction.py` |
| Data at rest after a session | Nothing written to disk; TTL eviction; read-only container filesystem | `services/store.py`, `Dockerfile` |
| Cross-site scripting | Strict CSP (`default-src 'self'`, no `unsafe-inline` script, no CDN), React escaping, no `dangerouslySetInnerHTML` anywhere | `core/security.py` |
| Clickjacking | `X-Frame-Options: DENY`, `frame-ancestors 'none'` | `core/security.py` |
| Information disclosure through errors | Typed error envelope; unexpected exceptions logged with traceback, returned without one | `core/errors.py`, `main.py` |
| Secret leakage | No secret in source; `SecretStr` in settings; `.env` git-ignored; CI greps for committed keys | `core/config.py`, `.github/workflows/ci.yml` |
| Vulnerable dependencies | Pinned versions, `pip-audit --strict`, `npm audit`, CodeQL, Dependabot | `.github/` |
| Container escalation | Non-root user, read-only application directory, all capabilities dropped, `no-new-privileges` | `Dockerfile`, `docker-compose.yml` |

---

## Privacy by design

The strongest control available to a tool handling potentially privileged legal
material is not encrypting data at rest — it is having nothing at rest.

- Uploaded documents exist only in process memory.
- They are evicted automatically after 30 minutes, and can be deleted
  immediately from the interface.
- Nothing is written to disk. The container's filesystem is read-only.
- Logs record identifiers, sizes and timings only. Document text and user
  questions are never logged.
- No account, no cookie, no session identifier, no analytics, no third-party
  script.

### Redaction before egress

Direct identifiers — email addresses, phone numbers, Aadhaar, PAN, card and IBAN
numbers — are replaced with stable placeholders (`[PAN_1]`) before any text
leaves the process, and restored in the response. The mapping lives in memory
for the duration of the request.

The pattern order matters and is tested: a 16-digit card number was, at one
point, partly consumed by the 12-digit Aadhaar pattern, leaving four digits in
the clear. Patterns now run longest-first, with a test per identifier class and
a round-trip test asserting `restore(redact(x)) == x`.

This reduces identifier exposure to the model provider. It is defence in depth,
not a compliance guarantee: a name in a contract is still a name.

---

## What is *not* defended

Stated explicitly, because a security document that only lists strengths is
marketing.

- **Prompt injection is mitigated, not solved.** Containment and refusal raise
  the cost of an attack. Neither is a proof. A sufficiently novel phrasing
  inside a document may still influence the model's tone or emphasis. The
  verification layer limits the blast radius — a fabricated clause is discarded
  regardless of why the model produced it — but it cannot prevent a suppressed
  one.
- **There is no authentication.** Any deployment is open to anyone who has the
  URL, rate-limited by address only. Behind a corporate boundary, put an
  authenticating proxy in front of it.
- **Rate limiting is per process and in memory.** It resets on restart and does
  not coordinate across replicas. A distributed deployment needs a shared
  backend such as Redis.
- **The model provider sees the document.** Redaction reduces direct
  identifiers; the substance is still transmitted to Google's API under their
  terms. Anyone for whom that is unacceptable should run a self-hosted model
  behind the same `LlmProvider` protocol.
- **Content is not scanned for malware.** Files are parsed for text and
  discarded; nothing is executed, no embedded reference is resolved, and no
  attachment is extracted. But no antivirus runs over the bytes.
- **Denial of service by cost.** An attacker within the rate limit can still
  consume API quota. A deployment that matters needs a spend cap at the provider.

---

## Dependency and supply-chain posture

- Every Python and JavaScript dependency is pinned to an exact version.
- `pip-audit --strict` and `npm audit --audit-level=high` run on every push.
- CodeQL runs the `security-and-quality` suite for both languages.
- Dependabot opens weekly update pull requests for pip, npm, Actions and Docker.
- The image installs no build toolchain into the runtime layer, and removes
  `pip`, `setuptools` and `wheel` after installation.
- CI fails if a Google API key pattern or a tracked `.env` file appears in the
  repository.

---

## Responsible-use boundary

LexiClear is built to inform, not to advise. Both system instructions forbid
telling the reader what to do, predicting how a court would rule, assessing
their position in a dispute, or stating that a document is safe to sign — and
both are asserted by tests. The not-legal-advice notice is attached to every
analysis response by the service, not by the interface, so it cannot be dropped
by a client. It is displayed on the results view and in the page footer, not
only at upload.
