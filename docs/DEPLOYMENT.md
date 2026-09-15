# Deployment

LexiClear ships as one container that serves the API and the built web client
from a single origin. That is a deliberate constraint rather than a packaging
convenience: it is what allows the Content-Security-Policy to stay at
`default-src 'self'` with no cross-origin exceptions, and it removes CORS from
the production path entirely.

Deploy the container anywhere that runs one. Two routes are documented below.

---

## Option A - Hugging Face Spaces (recommended)

Spaces runs a Docker image on port `7860` as uid `1000`, which is exactly what
the `Dockerfile` targets. It is free, needs no credit card, and the link stays
up.

1. Create a new Space: **SDK → Docker**, **Template → Blank**, visibility public.
2. Push this repository to the Space's git remote:

   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/lexiclear
   git push space main
   ```

3. In the Space, open **Settings → Variables and secrets** and add:

   | Name                        | Kind   | Value                          |
   | --------------------------- | ------ | ------------------------------ |
   | `LEXICLEAR_GOOGLE_API_KEY`  | Secret | your Gemini API key            |
   | `LEXICLEAR_ENVIRONMENT`     | Variable | `production`                 |
   | `LEXICLEAR_LLM_PROVIDER`    | Variable | `gemini`                     |

4. Wait for the build. The app is at
   `https://<your-username>-lexiclear.hf.space`, and
   `…/api/v1/health` should report `{"status":"ok"}`.

Secrets set this way are injected as environment variables at run time and are
never written into the image.

---

## Option B - Vercel (web client) plus a container host (API)

Vercel serves static output and serverless functions; it cannot run this
container, and the in-memory document store would not survive a serverless cold
start anyway. So the API goes to a container host and Vercel proxies to it.

1. Deploy the API container to Fly.io, Render, Railway or Cloud Run, and note
   its hostname.
2. In `vercel.json`, replace `LEXICLEAR_API_HOST` with that hostname.
3. Import the repository into Vercel. The build command and output directory in
   `vercel.json` are already correct.
4. Set `LEXICLEAR_CORS_ALLOW_ORIGINS` on the API to the Vercel domain.

The rewrite keeps the browser on one origin, so the strict CSP still holds.

---

## Configuration reference

Every setting is an environment variable prefixed `LEXICLEAR_`; see
[`.env.example`](../.env.example) for the full list with defaults. The only
required one is `LEXICLEAR_GOOGLE_API_KEY`, and only when
`LEXICLEAR_LLM_PROVIDER=gemini`.

Set `LEXICLEAR_ENVIRONMENT=production` in any public deployment. It switches
logging to JSON and enables `Strict-Transport-Security`, which should only be
sent over TLS.

## Scaling

The document store is process-local by design, so the image runs a single
worker: a second worker would serve requests that cannot see the first worker's
documents. To scale out, either put a session-affine load balancer in front of
several containers, or replace `DocumentStore` with a shared cache. The store is
a single class behind a narrow interface precisely so that substitution is a
contained change.

## Verifying a deployment

```bash
curl -s https://<host>/api/v1/health | jq
curl -sI https://<host>/ | grep -i 'content-security-policy\|x-frame-options'
```

Then run the end-to-end suite against it:

```bash
cd frontend && E2E_BASE_URL=https://<host> npm run test:e2e
```
