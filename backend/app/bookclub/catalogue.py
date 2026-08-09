import html
import json
import os
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx


# Shared BiblioCommons fetch/parse primitives below (CATALOGUE_HOST through
# fetch_catalogue_page) are also imported by lendery/catalogue.py for its own
# item-autofill scraping - don't remove or change their signatures without
# checking that consumer too.
CATALOGUE_HOST = "vaughanpl.bibliocommons.com"
RECORD_PATH = re.compile(r"^/v2/record/(S130C\d+)/?$")
MAX_RESPONSE_BYTES = 2_000_000

GOOGLE_BOOKS_SEARCH_URL = "https://www.googleapis.com/books/v1/volumes"
MAX_RESULTS = 10
PUBLICATION_YEAR_PATTERN = re.compile(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b")


class CatalogueImportError(ValueError):
    pass


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_state = False
        self.state_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        self.in_state = (
            tag == "script"
            and values.get("type") == "application/json"
            and values.get("data-iso-key") == "_0"
        )

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_state = False

    def handle_data(self, data: str) -> None:
        if self.in_state:
            self.state_parts.append(data)


def _validated_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    match = RECORD_PATH.fullmatch(parsed.path)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != CATALOGUE_HOST
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or match is None
    ):
        raise CatalogueImportError(
            "Enter a Vaughan Public Libraries catalogue record link."
        )
    canonical = f"https://{CATALOGUE_HOST}{parsed.path.rstrip('/')}"
    return canonical, match.group(1)


def clean_catalogue_text(value: str | None) -> str | None:
    if not value:
        return None
    value = html.unescape(value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    return value.strip() or None


def parse_catalogue_state(page: str) -> dict:
    parser = _MetadataParser()
    parser.feed(page)
    if not parser.state_parts:
        raise CatalogueImportError("The catalogue record did not include item data.")
    try:
        return json.loads("".join(parser.state_parts))
    except json.JSONDecodeError as exc:
        raise CatalogueImportError("The catalogue record could not be read.") from exc


def fetch_catalogue_page(value: str) -> tuple[str, str, str]:
    url, record_id = _validated_url(value)
    headers = {"User-Agent": "Libtools Catalogue Import/1.0"}
    try:
        with httpx.Client(timeout=12, headers=headers) as client:
            for _ in range(4):
                response = client.get(url, follow_redirects=False)
                if response.status_code not in (301, 302, 303, 307, 308):
                    break
                location = response.headers.get("location")
                if not location:
                    raise CatalogueImportError(
                        "The catalogue returned an invalid redirect."
                    )
                url, record_id = _validated_url(urljoin(url, location))
            else:
                raise CatalogueImportError("The catalogue redirected too many times.")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise CatalogueImportError(
            "Vaughan Public Libraries could not be reached. Try again shortly."
        ) from exc
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise CatalogueImportError("The catalogue response was unexpectedly large.")
    return response.text, url, record_id


def _api_key_param() -> dict[str, str]:
    key = os.getenv("GOOGLE_BOOKS_API_KEY")
    return {"key": key} if key else {}


def _extract_isbn(identifiers: list[dict] | None) -> str | None:
    by_type = {
        item.get("type"): item.get("identifier")
        for item in identifiers or []
        if item and item.get("identifier")
    }
    isbn = by_type.get("ISBN_13") or by_type.get("ISBN_10")
    if not isbn:
        return None
    return re.sub(r"[^0-9Xx]", "", isbn).upper() or None


def _parse_volume(item: dict) -> dict:
    info = item.get("volumeInfo") or {}
    images = info.get("imageLinks") or {}
    published = str(info.get("publishedDate") or "")
    year_match = PUBLICATION_YEAR_PATTERN.search(published)
    authors = info.get("authors") or []
    categories = info.get("categories") or []

    return {
        "external_id": item.get("id"),
        "title": clean_catalogue_text(info.get("title")),
        "author": "; ".join(authors) or None,
        "cover_image_url": images.get("thumbnail") or images.get("smallThumbnail"),
        "description": clean_catalogue_text(info.get("description")),
        "publication_date": (
            f"{year_match.group(1)}-01-01" if year_match else None
        ),
        "isbn": _extract_isbn(info.get("industryIdentifiers")),
        "publisher": info.get("publisher"),
        "page_count": info.get("pageCount"),
        "genres": ", ".join(dict.fromkeys(categories))[:500].rstrip(", ") or None,
        # Google Books has no first-class "series" field.
        "series": None,
        "catalogue_url": info.get("infoLink") or info.get("canonicalVolumeLink"),
    }


def search_catalogue_books(query: str) -> list[dict]:
    query = query.strip()
    if not query:
        raise CatalogueImportError("Enter a title or author to search.")

    params = {
        "q": query,
        "maxResults": MAX_RESULTS,
        "printType": "books",
        **_api_key_param(),
    }
    try:
        response = httpx.get(GOOGLE_BOOKS_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise CatalogueImportError(
            "Book search is currently unavailable. Try again shortly."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise CatalogueImportError(
            "Book search is currently unavailable. Try again shortly."
        ) from exc

    items = data.get("items") or []
    return [
        _parse_volume(item)
        for item in items
        if item and (item.get("volumeInfo") or {}).get("title")
    ]
