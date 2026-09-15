# Accessibility

LexiClear targets **WCAG 2.1 Level AA**. The people most likely to face a
contract they cannot afford a lawyer to read are disproportionately the people
least well served by inaccessible software, so accessibility here is part of the
problem statement rather than a finishing touch.

Conformance is enforced by the build, not asserted in a document: strict
`jsx-a11y` lint, axe-core in the unit suite, and axe-core again in a real
browser across both colour schemes, at 320 CSS pixels and at 200% zoom.

---

## Criterion map

| Criterion | Implementation | Verified by |
| --- | --- | --- |
| **1.1.1** Non-text content | Every icon is `aria-hidden`; each sits beside a text label | `jsx-a11y`, axe |
| **1.3.1** Info and relationships | Semantic landmarks, one `h1`, ordered headings, real `<blockquote cite>`, `<dl>` for metadata | axe, `App.test.tsx` |
| **1.3.2** Meaningful sequence | Single-column source order; the grid only reflows it | Playwright reflow test |
| **1.4.1** Use of colour | Risk is stated in words ("Read closely"), by border position, *and* by colour | `AnalysisPanel.test.tsx` |
| **1.4.3** Contrast (minimum) | All text pairs ≥ 4.5:1 in both themes; tokens documented in `theme.css` | axe in Playwright, light and dark |
| **1.4.4** Resize text | Relative units throughout; audited at 200% | Playwright zoom test |
| **1.4.10** Reflow | No horizontal scrolling at 320 CSS pixels | Playwright reflow test |
| **1.4.11** Non-text contrast | Borders on every raised surface, not shadow alone | axe |
| **1.4.12** Text spacing | No fixed heights on text containers; `line-height: 1.6` | Manual |
| **1.4.13** Content on hover | No hover-only content anywhere | By construction |
| **2.1.1** Keyboard | Every control reachable and operable; `Ctrl`/`Cmd`+`Enter` sends a question | Playwright keyboard journey |
| **2.1.2** No keyboard trap | No focus containment; no modals | Playwright |
| **2.4.1** Bypass blocks | Skip link is the first tab stop | `App.test.tsx`, Playwright |
| **2.4.3** Focus order | DOM order matches visual order; focus returns to the question field after an answer | `ChatPanel.test.tsx` |
| **2.4.6** Headings and labels | Descriptive headings; every control labelled | axe, Playwright |
| **2.4.7** Focus visible | 3px outline with 2px offset on `:focus-visible`, never removed | Manual, axe |
| **2.5.3** Label in name | Visible label text is the accessible name | axe |
| **2.5.8** Target size | 44×44 CSS pixel minimum on buttons and inputs | CSS `min-height` |
| **3.1.1** Language of page | `<html lang="en">` | axe |
| **3.2.2** On input | Nothing submits on change; the file input is the only exception and it is the primary action | By construction |
| **3.3.1** Error identification | Errors use `role="alert"`, in plain language, with a next step | `UploadPanel.test.tsx` |
| **3.3.2** Labels or instructions | Accepted formats, size limit and retention policy are in the input's `aria-describedby` | `UploadPanel.test.tsx` |
| **4.1.2** Name, role, value | Native elements throughout; no custom widget re-implements a native control | axe |
| **4.1.3** Status messages | `role="status"` for progress, `role="alert"` for errors, `role="log"` for the transcript | `App.test.tsx` |

---

## Decisions worth explaining

### Neumorphism, made accessible

The intended visual direction is soft extruded panels on a lilac-tinted ground
with bright saturated accents. Executed naively, that style fails WCAG: it
communicates elevation purely through low-contrast shadow.

What was done instead:

- Every raised or inset surface carries a **1px border as well as** its shadow,
  so the boundary survives low vision, glare and monochrome displays.
- A `@media (forced-colors: active)` block removes shadows entirely and replaces
  them with system borders, so Windows High Contrast mode gets a coherent layout
  rather than an undifferentiated wash.
- Text never sits on a shadowed gradient. Foreground and background are flat
  tokens whose contrast ratio is fixed and documented.
- Both themes are audited independently, because meeting contrast in light mode
  says nothing about dark mode.

### Announcing a streaming answer

Announcing a streamed answer token by token produces a stutter of single words
in a screen reader — technically "live", practically unusable. The transcript is
a `role="log"` region with `aria-live="polite"`, which announces appended
entries without re-reading earlier ones, and the completed answer is announced
once when the stream closes.

The polite live region carries a zero-width nonce, because screen readers ignore
a live region whose text has not changed — so a repeated message such as
"Analysis complete" after a second upload would otherwise be silently dropped.

### The file input is a real file input

The drop zone is a pointer-only enhancement layered over
`<input type="file">`. The input is visually hidden with `clip-path` rather than
`display: none`, because a display-hidden input is removed from the
accessibility tree entirely. Keyboard and screen-reader users operate it through
its `<label>`, which is styled as the primary button.

### Focus after an answer

The question field is disabled while an answer streams, and calling `focus()` on
a disabled element does nothing. An early implementation restored focus in the
same tick it re-enabled the field, so keyboard users were returned to the top of
the document after every question. Focus is now restored by an effect that runs
after the re-enabling render. A regression test asserts it.

---

## Running the audits

```bash
cd frontend
npm run test              # axe-core in jsdom, plus role and label assertions
npm run test:e2e          # axe-core in a real browser: contrast, reflow, zoom
```

The browser audit covers what jsdom cannot: colour contrast, computed focus
order and target size all require layout and painting.

## Known gaps

- The audits cover automated rules. Automated testing catches roughly a third of
  real accessibility barriers; no testing with actual screen-reader users has
  been carried out.
- The interface is English-only. For the audience this targets, multilingual
  output is the highest-value accessibility work remaining.
- There is no OCR, so a scanned document cannot be read at all. The failure is
  explicit and actionable rather than silent, but it is still a failure.
