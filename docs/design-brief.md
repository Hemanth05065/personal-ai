# Design brief — Local Assistant UI

Produced from `ui-ux-pro-max` (offline search), `frontend-design` (direction) and
`hallmark` (Floor rules, app-screen scope). Free and local: no web fonts, no CDN,
no new packages.

## Subject
A private assistant used by one person on their own machine. The screens are work
screens (chat, approvals, files, audit), so this is an **app**, not a landing page.
The tool should disappear into the task and feel trustworthy.

## Search results, and what was kept
| Query | Verdict |
|---|---|
| `--design-system` ("personal ai assistant ... security") | **Rejected.** Returned a sales-landing pattern and a red/blue "biomimetic" palette. Does not fit an app. |
| style: minimal dark productivity | **Kept.** Minimalism: clean, functional, high contrast, light and dark. |
| color: productivity / password manager | **Kept (adapted).** Teal action colour, secure green, slate neutrals. |
| typography | **Adapted.** Suggested Inter via Google Fonts. Replaced by the system font stack so the app never contacts the internet. |
| ux: destructive confirm, focus, loading | **Kept.** Confirm destructive actions, visible focus rings, skeletons with `aria-busy`. |

## Direction (frontend-design)
Calm, utilitarian, a little warm. The current "near-black plus mint accent, Georgia
headings, tracked-caps labels" is the generic AI default, so it goes.

**Tokens** (all declared once at `:root`). **Black and white**, by the owner's
choice (13 Nov 2026). It replaced a teal accent and a dark mode. Red is kept only
for destructive actions and alarms. Every status also has a text label, so nothing
depends on colour.

| Role | Value |
|---|---|
| bg / surface / surface-2 | #fafafa / #ffffff / #f0f0f0 |
| border / border-strong | #dcdcdc / #8a8a8a |
| text / muted | #000000 / #555555 |
| accent (primary action, selection) | #000000 on #ffffff, soft #ebebeb |
| danger | #b42318 |
| warn / good | black (the text label carries the meaning) |

**Type:** one family, system stack (Segoe UI Variable / system-ui), mono for file
previews. Scale ratio 1.125 on a 16px body. Labels are the body face, one step
smaller, sentence case, untracked.

**Layout:** sidebar kept because it carries the conversation list (a real
function), collapsing to a top bar with a menu below 60rem. Content is a capped
column (max about 70ch for reading, wider for tables). Tables and rows before cards.

## Signature
A **safety strip** in the top bar on every screen: emergency state, audit chain
valid, approvals waiting (links to the inbox). It is the one thing this assistant is
known for, and it uses only real data from `/security/status`.

## Interaction rules
- Destructive actions confirm **inline** (button turns into "Delete / Cancel"), not
  with `window.confirm`. Emergency stop expands an inline reason field.
- Every region that loads data has four states: loading (skeleton), empty (what
  belongs here and the one action), error (what broke and what to do), full.
- Chat replies render markdown safely (React elements only, no raw HTML).
- Current view lives in the URL hash so reload and back work.
- Motion is state only (150 ms), `transform`/`opacity`, reduced-motion respected.

## Floor checklist (hallmark, binding)
Tokens only at `:root`; no `transition: all`; focus-visible on every control;
reduced-motion fallback; `overflow-x: clip` on html and body; no uppercase or
tracked labels; no middle-dot meta strings; no gradients as decoration; no
emoji icons; contrast 4.5:1 minimum; touch targets 44px.

## Out of scope for this phase
Streaming replies (Phase 3), new backend endpoints, web fonts, new npm packages.
