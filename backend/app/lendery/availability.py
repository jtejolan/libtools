from dataclasses import dataclass
import re
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx


TRACKED_BRANCH_CODE = "9"
TRACKED_BRANCH_NAME = "Pierre Berton Resource Library"
AVAILABILITY_STATUS_VERSION = 2
CATALOG_HOST = "vaughanpl.bibliocommons.com"
AVAILABILITY_ENDPOINT = (
    "https://gateway.bibliocommons.com/v2/libraries/"
    "vaughanpl/bibs/{metadata_id}/availability"
)
RECORD_PATH = re.compile(r"/v2/record/(S130C\d+)/?")

AvailabilityStatus = Literal[
    "available",
    "checked_out",
    "unavailable",
    "not_held",
    "unknown",
]


class AvailabilityCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class AvailabilityResult:
    status: AvailabilityStatus
    available_copies: int
    total_copies_at_branch: int
    matched_specific_copy: bool = False


def metadata_id_from_url(library_url: str) -> str:
    parsed = urlsplit(library_url)
    match = RECORD_PATH.fullmatch(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.hostname != CATALOG_HOST
        or match is None
    ):
        raise AvailabilityCheckError(
            "The catalogue URL is not a valid Vaughan BiblioCommons record"
        )
    return match.group(1)


def parse_availability(
    payload: Any, barcode: str | None = None
) -> AvailabilityResult:
    try:
        availability_summary = payload["availability"]
        error_classification = availability_summary["errorClassification"]
        entities = payload["entities"]
        bib_items = entities["bibItems"]
    except (KeyError, TypeError) as exc:
        raise AvailabilityCheckError(
            "BiblioCommons returned an unexpected availability response"
        ) from exc

    if error_classification:
        raise AvailabilityCheckError(
            "BiblioCommons could not determine availability"
        )

    if not isinstance(bib_items, dict):
        raise AvailabilityCheckError(
            "BiblioCommons returned an unexpected item list"
        )

    branch_items = [
        item
        for item in bib_items.values()
        if isinstance(item, dict)
        and str(item.get("branch", {}).get("code")) == TRACKED_BRANCH_CODE
    ]
    if not branch_items:
        metadata_id = availability_summary.get("metadataId")
        overall_availability = entities.get("availabilities", {}).get(
            metadata_id,
            {},
        )
        if (
            not bib_items
            and overall_availability.get("statusType") == "UNAVAILABLE"
        ):
            return AvailabilityResult(
                status="unavailable",
                available_copies=0,
                total_copies_at_branch=0,
            )
        return AvailabilityResult(
            status="not_held",
            available_copies=0,
            total_copies_at_branch=0,
        )

    available_copies = sum(
        1
        for item in branch_items
        if item.get("availability", {}).get("statusType") == "AVAILABLE"
    )

    # Two Lendery items can legitimately share a library_url (duplicate
    # physical copies of the same catalogue title). BiblioCommons' itemId
    # is shaped "{bibId}|{barcode}||{sequence}" and that barcode segment is
    # the same physical barcode staff enter into Lendery, so when we can
    # match it we report THIS copy's own status instead of "is any copy of
    # the title available" — otherwise duplicates would be indistinguishable.
    matched_item = None
    if barcode:
        for candidate in branch_items:
            item_id = candidate.get("itemId")
            if not isinstance(item_id, str):
                continue
            parts = item_id.split("|")
            if len(parts) > 1 and parts[1] == barcode:
                matched_item = candidate
                break

    if matched_item is not None:
        copy_availability = matched_item.get("availability", {})
        if copy_availability.get("statusType") == "AVAILABLE":
            status: AvailabilityStatus = "available"
        elif (
            copy_availability.get("statusType") == "UNAVAILABLE"
            and copy_availability.get("status") == "CHECKED_OUT"
        ):
            status = "checked_out"
        else:
            status = "unavailable"
    elif available_copies:
        status = "available"
    elif all(
        item.get("availability", {}).get("status") == "CHECKED_OUT"
        for item in branch_items
    ):
        status = "checked_out"
    else:
        status = "unavailable"

    return AvailabilityResult(
        status=status,
        available_copies=available_copies,
        total_copies_at_branch=len(branch_items),
        matched_specific_copy=matched_item is not None,
    )


def suggest_unclaimed_barcode(
    payload: Any, existing_barcodes: set[str]
) -> str | None:
    """Suggest a barcode for a new Lendery item from a raw BiblioCommons
    availability payload: the one Pierre Berton copy whose barcode isn't
    already tracked as another item's barcode. Returns None rather than
    guessing when that isn't true of exactly one copy — zero untracked
    copies, or more than one (too ambiguous to know which physical copy is
    being added) — or when the payload is missing/malformed.
    """
    try:
        bib_items = payload["entities"]["bibItems"]
    except (KeyError, TypeError):
        return None
    if not isinstance(bib_items, dict):
        return None

    candidates = []
    for item in bib_items.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("branch", {}).get("code")) != TRACKED_BRANCH_CODE:
            continue
        item_id = item.get("itemId")
        if not isinstance(item_id, str):
            continue
        parts = item_id.split("|")
        if len(parts) > 1 and parts[1] and parts[1] not in existing_barcodes:
            candidates.append(parts[1])

    return candidates[0] if len(candidates) == 1 else None


_shared_client: httpx.Client | None = None


def _default_client() -> httpx.Client:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.Client(
            timeout=httpx.Timeout(8.0),
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "LenderyAvailability/1.0",
            },
        )
    return _shared_client


def fetch_availability_payload(
    library_url: str,
    *,
    client: httpx.Client | None = None,
) -> Any:
    metadata_id = metadata_id_from_url(library_url)
    endpoint = AVAILABILITY_ENDPOINT.format(metadata_id=metadata_id)
    if client is None:
        client = _default_client()

    try:
        response = client.get(endpoint)
        response.raise_for_status()
        return response.json()
    except AvailabilityCheckError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise AvailabilityCheckError(
            "Could not retrieve availability from BiblioCommons"
        ) from exc


def check_availability(
    library_url: str,
    barcode: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> AvailabilityResult:
    payload = fetch_availability_payload(library_url, client=client)
    return parse_availability(payload, barcode)
