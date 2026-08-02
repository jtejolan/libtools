import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx


CATALOGUE_HOST = "vaughanpl.bibliocommons.com"
RECORD_PATH = re.compile(r"^/v2/record/(S130C\d+)/?$")
MAX_RESPONSE_BYTES = 2_000_000


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


def _display_author(value: str) -> str:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) == 2 and all(parts):
        return f"{parts[1]} {parts[0]}"
    return value.strip()


def _field_values(record: dict, field_name: str) -> list[str]:
    result: list[str] = []
    for group in record.get("fields", []):
        for item in group.get("items", []):
            if item.get("fieldName") != field_name:
                continue
            for field_value in item.get("fieldValues", []):
                result.extend(field_value.get("primary", {}).get("values", []))
    return result


def parse_catalogue_record(
    page: str, catalogue_url: str, record_id: str
) -> dict:
    state = parse_catalogue_state(page)
    try:
        record = state["entities"]["catalogBibs"][record_id]
        brief = record["brief"]
    except (KeyError, TypeError) as exc:
        raise CatalogueImportError("The catalogue record could not be read.") from exc


    creators = brief.get("creators") or []
    authors = [
        _display_author(item["fullName"])
        for item in creators
        if item.get("fullName")
    ]
    isbn_values = _field_values(record, "ISBN") or brief.get("isbns", [])
    isbn = next(
        (
            value
            for value in isbn_values
            if len(re.sub(r"\D", "", value)) == 13
        ),
        None,
    )
    isbn = isbn or next(iter(isbn_values), None)
    if isbn:
        isbn = re.sub(r"[^0-9Xx]", "", isbn).upper()

    publication = next(iter(_field_values(record, "PUBLICATION")), "")
    publisher_match = re.search(r":\s*([^,;]+)", publication)
    publisher = publisher_match.group(1).strip() if publisher_match else None
    page_text = " ".join(_field_values(record, "DESCRIPTION"))
    page_match = re.search(r"(\d[\d,]*)\s+pages?\b", page_text, re.IGNORECASE)
    page_count = int(page_match.group(1).replace(",", "")) if page_match else None

    subjects = _field_values(record, "GENRE") + _field_values(record, "SUBJECT")
    genres = ", ".join(dict.fromkeys(value.strip(" .") for value in subjects))
    genres = genres[:500].rstrip(", ") or None
    series_values = _field_values(record, "SERIES")
    series = ", ".join(dict.fromkeys(value.strip(" .") for value in series_values))
    series = series[:300].rstrip(", ") or None
    publication_year = re.search(
        r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b",
        str(brief.get("publicationDate", "")),
    )

    cover = brief.get("coverImage") or {}
    return {
        "title": clean_catalogue_text(brief.get("title")),
        "author": "; ".join(authors) or None,
        "cover_image_url": (
            cover.get("large") or cover.get("medium") or cover.get("small")
        ),
        "description": clean_catalogue_text(brief.get("description")),
        "publication_date": (
            f"{publication_year.group(1)}-01-01" if publication_year else None
        ),
        "isbn": isbn,
        "publisher": publisher,
        "page_count": page_count,
        "genres": genres,
        "series": series,
        "catalogue_url": catalogue_url,
    }


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


def fetch_catalogue_book(value: str) -> dict:
    page, url, record_id = fetch_catalogue_page(value)
    return parse_catalogue_record(page, url, record_id)
