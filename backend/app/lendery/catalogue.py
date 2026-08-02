from urllib.parse import urlsplit

from bookclub.catalogue import (
    CatalogueImportError,
    clean_catalogue_text,
    fetch_catalogue_page,
    parse_catalogue_state,
)


def _safe_external_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def _first_online_resource(state: dict, record: dict, record_id: str) -> str | None:
    try:
        value = state["entities"]["bibs"][record_id]["availability"][
            "eresourceUrl"
        ]
    except (KeyError, TypeError):
        value = None
    resource = _safe_external_url(value)
    if resource:
        return resource

    for group in record.get("fields", []):
        for item in group.get("items", []):
            for field_value in item.get("fieldValues", []):
                resource = _safe_external_url(field_value.get("sourceURI"))
                if resource:
                    return resource
                for candidate in field_value.get("primary", {}).get("values", []):
                    resource = _safe_external_url(candidate)
                    if resource:
                        return resource
    return None


def parse_catalogue_item(page: str, library_url: str, record_id: str) -> dict:
    state = parse_catalogue_state(page)
    try:
        record = state["entities"]["catalogBibs"][record_id]
        brief = record["brief"]
    except (KeyError, TypeError) as exc:
        raise CatalogueImportError("The catalogue record could not be read.") from exc

    cover = brief.get("coverImage") or {}
    return {
        "name": clean_catalogue_text(brief.get("title")),
        "description": clean_catalogue_text(brief.get("description")),
        "image_url": (
            cover.get("large") or cover.get("medium") or cover.get("small")
        ),
        "manual_url": _first_online_resource(state, record, record_id),
        "library_url": library_url,
    }


def fetch_catalogue_item(value: str) -> dict:
    page, url, record_id = fetch_catalogue_page(value)
    return parse_catalogue_item(page, url, record_id)
