# Coding guidelines

Commands, test running, the `models.py`/`schemas.py`/`crud.py`/`routes.py`
package shape, and the Alembic migration workflow are already covered well
in the root `CLAUDE.md` — this file covers conventions CLAUDE.md doesn't,
each cited to where it actually appears in code.

## `required_values_cannot_be_null` validator

Appears in `bookclub/schemas.py` and `lendery/schemas.py`, on the `*Update`
(PATCH) schemas. Those schemas make every field `Optional` so a client can
*omit* a field to leave it unchanged — but a handful of fields (e.g.
`LenderyItemUpdate.name`, `.barcode`, `.physical_manual_missing`,
`.checkin_card_missing`) must never be explicitly set to `null` if the
client does send the key. The validator:

```python
@field_validator("name", "barcode", ...)
@classmethod
def required_values_cannot_be_null(cls, value: object) -> object:
    if value is None:
        raise ValueError("field cannot be null")
    return value
```

When adding a new required-but-omittable field to an `*Update` schema, add
it to this validator's field list too.

## `PublicXResponse` pattern

Every `/api/public/*` route returns a narrow, hand-picked response schema
instead of the full model schema: `PublicClubResponse`,
`PublicMeetingResponse`, `PublicShelfBookResponse` (bookclub),
`PublicLenderyItemResponse`, `PublicComponentResponse` (lendery). Rule:
**never expose a full `XResponse` schema on a public route** — define a
`PublicXResponse` that lists only the fields safe for an anonymous visitor,
even if it duplicates a few field declarations.

## `ItemActivity` snapshot-for-survival pattern

`lendery/models.py`'s `ItemActivity` copies item identity fields (barcode,
name, category) onto each activity row and keeps `original_item_id` even
after the FK `item_id` is nulled (`ondelete="SET NULL"`). This is the
pattern to follow for any append-only audit log that must outlive deletion
of the record it's about: snapshot the fields you'll need to display later,
don't rely on the live FK relationship.

## Password hashing

scrypt, not bcrypt/argon2 (`backend/app/security.py`,
`hash_password`/`verify_password`). Don't swap libraries without a reason —
see `docs/backend/shared.md`.

## Testing

`unittest`, not pytest — run from `backend/` with
`PYTHONPATH=app .venv/bin/python -m unittest discover -s tests -v`. See root
`CLAUDE.md` for exact commands, including running a single test file/case.

## Frontend fetch wrapper

Each frontend page independently defines its own `request()`/`requestJson()`
fetch wrapper (auth headers, JSON parsing, error handling) — there is no
shared `api.js`. This is an established, consistent convention across every
page (see `docs/frontend/overview.md`), not an oversight — don't introduce a
shared module unless the task specifically calls for that refactor.

## No enforced style

There is no lint/format config anywhere in this repo (no ruff/flake8/eslint
configs, confirmed in `docs/dependency-map.md`'s external deps list — none
are lint tools). Don't invent style rules that aren't already enforced by
existing code or stated in `CLAUDE.md`.
