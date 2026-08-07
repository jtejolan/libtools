# bookclub/

Multi-tenant book club manager. Every club-owned table is scoped by
`club_id`, and uniqueness constraints (email, ISBN, template key) are scoped
**per club**, not global. Available to every signed-in Libtools account
(not gated by `ToolAccess` — see `docs/backend/accounts.md`).

## Models (`bookclub/models.py`, 269 lines)

| Model | Table | Purpose |
|---|---|---|
| `BookClub` | `book_clubs` | A club: name, slug, `public` flag, organizer info |
| `BookClubAccess` | `book_club_access` | User-to-club grant (`role`, e.g. owner) |
| `BookClubMember` | `bookclub_members` | A club's member roster; unique per `(club_id, email)`; carries delivery details plus transit-label/email timestamps |
| `BookClubBook` | `bookclub_books` | A book the club has read/will read; unique per `(club_id, isbn)`; can be flagged as an undated past selection |
| `BookClubMeeting` | `bookclub_meetings` | A dated session tied to one book, with `meeting_duration_minutes`, an `archived_at` display-mode flag, and discussion notes; `book_title`/`book_author` are denormalized copies kept in sync on write. `starts_at`/`ends_at` are computed `@property`s (not columns), from `bookclub/scheduling.py` |
| `BookClubParticipation` | `bookclub_participation` | Member roster for one meeting (`attended` flag plus session-only participant note); unique per `(meeting_id, member_id)` |
| `BookClubTemplate` | `bookclub_templates` | Editable email template; unique per `(club_id, key)` |
| `BookClubDiscussionQuestion` | `bookclub_discussion_questions` | Legacy ordered questions retained for API compatibility; migration `e93f1a6b2c47` copies existing text into meeting discussion notes |

## Routes

| Router | Prefix | File | Endpoints | Purpose |
|---|---|---|---|---|
| `router` | `/bookclub/clubs` | `club_routes.py` | 5 | Club CRUD, select-into-session, list accessible clubs |
| `public_router` | `/api/public/clubs` | `club_routes.py` | 1 | `GET /{slug}` — public read-only club page |
| `router` | `/bookclub` | `routes.py` | 44 | Members, books (incl. catalogue import), meetings, roster/participation, onboarding/arrival email preview/send/**mark-sent** and reminder preview/send, giveaway draw, templates, transit labels, discussion questions — whole router requires `require_selected_club` |

## Other modules

- `access.py` — `slugify()`, `accessible_club_statement()` (admins see all
  clubs, others only clubs they have `BookClubAccess` to),
  `require_bookclub_tool` (blocks users with `must_change_password` set),
  `require_selected_club` (reads `bookclub_id` from the session, 409s if
  none selected, 403s if the user can't access it — exported as the
  `SelectedClub` dependency type).
- `catalogue.py` — scrapes Vaughan PL (BiblioCommons) pages to autofill book
  metadata (title/author/ISBN/cover/etc). `lendery/catalogue.py` does the
  same kind of scraping for item metadata but is a **separate, unshared**
  implementation — a markup/parsing fix here does not automatically apply
  there. See `docs/backend/lendery.md`.
- `scheduling.py` (34 lines) — `parse_meeting_time()` (free-text, 5 known
  formats) and `meeting_datetime_range()`. Lives outside both `models.py`
  and `crud.py` so each can import it without a circular dependency;
  `models.py`'s `starts_at`/`ends_at` properties and `crud.py`'s
  `build_calendar_link()` both use it.
- `crud.py` (1,031 lines) — DB operations for every model above.
- `email_delivery.py` (26 lines) — thin plain-text wrapper over the shared
  `backend/app/email_delivery.py`.

## Gotchas

- Most of `routes.py` depends on `SelectedClub` (from `require_selected_club`),
  **not** just `BookClubUser` — a request without a club selected in the
  session gets a 409, not a 401/403.
- Public read-only access lives in `club_routes.py`'s `public_router`, not
  in `routes.py` — don't look for it there.
- Uniqueness is per-club everywhere: two different clubs can have members
  with the same email, books with the same ISBN, or templates with the same
  key. Only `BookClub.slug` is globally unique.
- `BookClubMeeting.book_title`/`book_author` are denormalized snapshots kept
  in sync with the linked `BookClubBook` on write, retained for
  backwards-compatible migrations — don't treat them as the source of truth,
  edit via the book relationship.
- Printing a transit label records `transit_label_printed_at`; the UI treats a
  later print than `arrival_email_sent_at` as a fresh arrival-confirmation task.
- Member deletion explicitly clears saved giveaway-winner references and
  participation rows before removing the member, so it is reliable even when
  SQLite foreign-key enforcement differs between environments.
- `accounts/bootstrap.py` imports `bookclub.models` to seed club access at
  startup — this is a one-way, bootstrap-time-only dependency (see
  `docs/dependency-map.md`), not a sign that `accounts` generally depends on
  `bookclub`.
- `BookClubMeeting.status` only has two valid *write* values:
  `"planned"`/`"completed"` (`Literal` in `MeetingBase`/`MeetingUpdate`).
  `"in_progress"` is **never stored** — it's a frontend-computed display
  state (now vs. `starts_at`/`ends_at`). `"cancelled"` doesn't exist at all —
  a meeting the club no longer wants is deleted, not cancelled. Migration
  `f06fece22726` (current head) normalizes any pre-existing
  `cancelled`/`in_progress` rows to `"planned"` — but that's a one-time
  UPDATE, not an enforced constraint, so a row can still end up with a
  stale/legacy status value outside dev flows the migration didn't run
  against (e.g. a `librarytools.db` snapshot committed from an
  earlier/parallel state — this bit us once). `MeetingResponse.status` is
  therefore deliberately widened back to plain `str` (not the `Literal`) so
  reading a bad legacy value reports it instead of 500ing the whole list —
  only writes stay strict.
- `archived_at` (same migration) is a plain settable field via the generic
  `PATCH /bookclub/meetings/{id}` — unlike the email-sent timestamps below,
  it's a display-mode toggle (which view a session opens to by default), not
  an audit trail, so it doesn't get a dedicated endpoint.
- The onboarding/arrival-email `mark-sent` endpoints
  (`.../onboarding-email/mark-sent`, `.../arrival-email/mark-sent`) record
  the sent-timestamp **without** calling `email_delivery` — for staff who
  sent the email manually (e.g. copy-pasted the composed text) and want the
  pending-followup badge cleared. `MemberUpdate` deliberately does **not**
  expose `onboarding_email_sent_at`/`arrival_email_sent_at` — these two
  endpoints are the only way to set them outside of an actual send.

## Where to look for X

| Task | Files to touch |
|---|---|
| Add a new club-scoped entity | `bookclub/models.py` (remember `club_id` FK + per-club `UniqueConstraint`), `schemas.py`, `crud.py`, `routes.py` |
| Change what's visible on the public club page | `bookclub/club_routes.py` (`public_router`), `schemas.py` (`PublicClubResponse`) |
| Add a new email template kind | `bookclub/models.py` (`BookClubTemplate.kind`), `crud.py`, `routes.py`, `email_delivery.py` |
| Change catalogue import parsing | `bookclub/catalogue.py` — remember `lendery/catalogue.py` does its own separate scraping and won't pick up the fix |
| Change how meeting time/duration is parsed or computed | `bookclub/scheduling.py` (used by both `models.py` and `crud.py`) |
| Add a manual "mark as sent" action for a new email type | `bookclub/crud.py` (mirror `mark_onboarding_email_sent`), `routes.py` (mirror the `.../mark-sent` route) |
