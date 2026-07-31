from dataclasses import dataclass
import re
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx


TRACKED_BRANCH_CODE = "9"
TRACKED_BRANCH_NAME = "Pierre Berton Resource Library"
CATALOG_HOST = "vaughanpl.bibliocommons.com"
AVAILABILITY_ENDPOINT = (
    "https://gateway.bibliocommons.com/v2/libraries/"
    "vaughanpl/bibs/{metadata_id}/availability"
)
RECORD_PATH = re.compile(r"/v2/record/(S130C\d+)/?")

AvailabilityStatus = Literal[
    "available",
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


def parse_availability(payload: Any) -> AvailabilityResult:
    try:
        error_classification = payload["availability"]["errorClassification"]
        bib_items = payload["entities"]["bibItems"]
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
    return AvailabilityResult(
        status="available" if available_copies else "unavailable",
        available_copies=available_copies,
        total_copies_at_branch=len(branch_items),
    )


def check_availability(
    library_url: str,
    *,
    client: httpx.Client | None = None,
) -> AvailabilityResult:
    metadata_id = metadata_id_from_url(library_url)
    endpoint = AVAILABILITY_ENDPOINT.format(metadata_id=metadata_id)
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(8.0),
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "LenderyAvailability/1.0",
            },
        )

    try:
        response = client.get(endpoint)
        response.raise_for_status()
        return parse_availability(response.json())
    except AvailabilityCheckError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise AvailabilityCheckError(
            "Could not retrieve availability from BiblioCommons"
        ) from exc
    finally:
        if owns_client:
            client.close()
