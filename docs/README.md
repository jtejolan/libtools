# /docs — AI-context index

This directory is a context index for Claude Code sessions working in this
repo — more granular than the root `CLAUDE.md`, and not meant for
human end-users (that's `README.md`'s job) or as a restatement of features
(also `README.md`). Before working on a package or frontend page you haven't
touched recently, read this file to find the 1-2 relevant docs instead of
grepping/reading source files cold.

**Keeping it current**: see the "AI-context docs" section in the root
`CLAUDE.md` for the maintenance rule. Short version — small, targeted edits
to the specific file below a change affects, never a full regenerate.

| File | Covers |
|---|---|
| `code-index.md` | Every source file: path, line count, one-line purpose, which doc has more detail |
| `dependency-map.md` | Internal cross-package import graph + external dependency table |
| `architecture.md` | Cross-package narrative: request flow, the dual-ASGI-app trick, auth/sessions, multi-tenancy, migrations, deployment shape |
| `coding-guidelines.md` | Observed conventions with concrete code citations (validator patterns, public-response pattern, etc.) |
| `backend/accounts.md` | Accounts/auth package: models, routes, gotchas |
| `backend/bookclub.md` | Book Club Manager package: models, routes, gotchas |
| `backend/lendery.md` | Lendery inventory package: models, routes, gotchas |
| `backend/shared.md` | Shared top-level backend modules: `main.py`, `database.py`, `dependencies.py`, `security.py`, `email_delivery.py` |
| `frontend/overview.md` | No-build-step orientation, shared JS/CSS files, full page inventory |
| `frontend/accounts.md` | Login/register/admin/dashboard/homepage pages |
| `frontend/bookclub.md` | Book Club app + public club page |
| `frontend/lendery.md` | Lendery app, export UI, public quick-check page |
