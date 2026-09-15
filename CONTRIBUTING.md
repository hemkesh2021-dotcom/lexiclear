# Contributing

## Setup

```bash
make install     # backend venv + frontend node_modules
make dev         # API on :8000, web client on :5173
```

No API key is needed to develop: `LEXICLEAR_LLM_PROVIDER=mock` runs the entire
product offline.

## Before opening a pull request

```bash
make check       # exactly what CI runs: lint, types, tests, security
```

CI will not pass anything `make check` rejects.

## Standards

- **Types.** `mypy --strict` and `tsc` with `strict` plus
  `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`. No `Any` escapes,
  no `@ts-ignore`.
- **Coverage.** 90% backend, 90% frontend statements. New code arrives with
  tests.
- **Accessibility.** `jsx-a11y` strict rules are errors. Any new interactive
  surface needs an axe assertion in its component test.
- **Docstrings.** Every public module, class and function. Explain *why*, not
  what the signature already says. Non-obvious decisions get a comment naming
  the alternative that was rejected.
- **Security.** No new dependency without a reason that could be defended in
  review. Anything touching the upload path, the prompt path or the error path
  needs a test in the corresponding security suite.

## Layout

Keep routes thin. A route validates, delegates to a service, and serialises. If
pipeline logic is appearing in `api/v1/`, it belongs in `services/`.

Vendor SDK code stays in `app/llm/`. Everything else depends on the
`LlmProvider` protocol, which is what keeps the test suite offline.

## Commits

Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
