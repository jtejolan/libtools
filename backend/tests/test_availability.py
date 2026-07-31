import unittest

import httpx
from pydantic import ValidationError

from lendery.availability import (
    AvailabilityCheckError,
    check_availability,
    metadata_id_from_url,
    parse_availability,
)
from lendery.schemas import LenderyItemCreate


def payload_with_items(*items: dict) -> dict:
    return {
        "availability": {
            "errorClassification": None,
        },
        "entities": {
            "bibItems": {
                str(index): item
                for index, item in enumerate(items)
            }
        }
    }


def item(branch_code: str, status: str) -> dict:
    return {
        "branch": {
            "code": branch_code,
            "name": (
                "Pierre Berton Resource Library"
                if branch_code == "9"
                else "Bathurst Clark Resource Library"
            ),
        },
        "availability": {
            "statusType": status,
        },
    }


class AvailabilityParserTests(unittest.TestCase):
    def test_available_when_any_pierre_berton_copy_is_available(self) -> None:
        result = parse_availability(
            payload_with_items(
                item("9", "AVAILABLE"),
                item("9", "UNAVAILABLE"),
                item("4", "AVAILABLE"),
            )
        )

        self.assertEqual(result.status, "available")
        self.assertEqual(result.available_copies, 1)
        self.assertEqual(result.total_copies_at_branch, 2)

    def test_ignores_available_copies_at_other_branches(self) -> None:
        result = parse_availability(
            payload_with_items(
                item("9", "UNAVAILABLE"),
                item("4", "AVAILABLE"),
            )
        )

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.available_copies, 0)
        self.assertEqual(result.total_copies_at_branch, 1)

    def test_not_held_when_pierre_berton_has_no_copies(self) -> None:
        result = parse_availability(
            payload_with_items(item("4", "AVAILABLE"))
        )

        self.assertEqual(result.status, "not_held")
        self.assertEqual(result.total_copies_at_branch, 0)

    def test_unexpected_response_is_an_unknown_check_error(self) -> None:
        with self.assertRaises(AvailabilityCheckError):
            parse_availability({"entities": {}})

    def test_catalogue_error_is_not_treated_as_not_held(self) -> None:
        payload = payload_with_items()
        payload["availability"]["errorClassification"] = (
            "ServiceUnavailable"
        )

        with self.assertRaises(AvailabilityCheckError):
            parse_availability(payload)

    def test_checker_uses_fixed_gateway_endpoint(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                str(request.url),
                "https://gateway.bibliocommons.com/v2/libraries/"
                "vaughanpl/bibs/S130C603511/availability",
            )
            return httpx.Response(
                200,
                json=payload_with_items(item("9", "AVAILABLE")),
            )

        with httpx.Client(
            transport=httpx.MockTransport(handler)
        ) as client:
            result = check_availability(
                "https://vaughanpl.bibliocommons.com/"
                "v2/record/S130C603511",
                client=client,
            )

        self.assertEqual(result.status, "available")


class LibraryUrlValidationTests(unittest.TestCase):
    def test_extracts_metadata_id(self) -> None:
        self.assertEqual(
            metadata_id_from_url(
                "https://vaughanpl.bibliocommons.com/"
                "v2/record/S130C603511"
            ),
            "S130C603511",
        )

    def test_schema_rejects_arbitrary_urls(self) -> None:
        with self.assertRaises(ValidationError):
            LenderyItemCreate(
                name="Unsafe",
                barcode="UNSAFE-1",
                library_url="https://example.com/v2/record/S130C603511",
            )

    def test_schema_accepts_vaughan_record_url(self) -> None:
        model = LenderyItemCreate(
            name="Carpet cleaner",
            barcode="LENDERY-1",
            library_url=(
                "https://vaughanpl.bibliocommons.com/"
                "v2/record/S130C603511"
            ),
        )

        self.assertEqual(
            str(model.library_url),
            "https://vaughanpl.bibliocommons.com/"
            "v2/record/S130C603511",
        )


if __name__ == "__main__":
    unittest.main()
