# Library Tools

A cozy home for practical library software. The FastAPI service serves the
project homepage at `/`, the Lendery inventory workspace at `/lendery`, the
interactive API documentation at `/docs`, and the Lendery endpoints below the
same `/lendery` namespace.

## Pierre Berton availability

Add a Vaughan BiblioCommons record URL to an item's `library_url` field. Opening
that item refreshes its status using only copies at Pierre Berton Resource
Library; copies at every other branch are ignored. The saved status is one of
`available`, `unavailable`, `not_held`, or `unknown`.

Filter saved statuses through the list API:

```text
GET /lendery/items?availability=in
GET /lendery/items?availability=out
GET /lendery/items?availability=not_held
GET /lendery/items?availability=unknown
```

An availability failure keeps the previous status and records the failed check
instead of marking the item out.

## Run locally

```sh
cd backend/app
uvicorn main:app --reload
```
