import unittest
from unittest.mock import Mock, patch

import httpx

from bookclub.catalogue import (
    CatalogueImportError,
    _extract_isbn,
    _parse_volume,
    search_catalogue_books,
)


class CatalogueIsbnTests(unittest.TestCase):
    def test_prefers_isbn_13_over_isbn_10(self) -> None:
        identifiers = [
            {"type": "ISBN_10", "identifier": "0593135202"},
            {"type": "ISBN_13", "identifier": "9780593135204"},
        ]
        self.assertEqual(_extract_isbn(identifiers), "9780593135204")

    def test_falls_back_to_isbn_10_when_no_isbn_13(self) -> None:
        identifiers = [{"type": "ISBN_10", "identifier": "0593135202"}]
        self.assertEqual(_extract_isbn(identifiers), "0593135202")

    def test_returns_none_when_no_identifiers(self) -> None:
        self.assertIsNone(_extract_isbn(None))
        self.assertIsNone(_extract_isbn([]))
        self.assertIsNone(_extract_isbn([{"type": "OTHER", "identifier": "123"}]))


class CatalogueParseVolumeTests(unittest.TestCase):
    def test_parses_a_full_volume(self) -> None:
        item = {
            "id": "abc123",
            "volumeInfo": {
                "title": "Project Hail Mary",
                "authors": ["Andy Weir"],
                "publisher": "Ballantine Books",
                "publishedDate": "2021-05-04",
                "description": "An astronaut&lt;br /&gt;&lt;br /&gt;saves Earth.",
                "industryIdentifiers": [
                    {"type": "ISBN_10", "identifier": "0593135202"},
                    {"type": "ISBN_13", "identifier": "9780593135204"},
                ],
                "pageCount": 476,
                "categories": ["Science fiction", "Science fiction"],
                "imageLinks": {
                    "thumbnail": "https://books.google.com/thumb.jpg",
                    "smallThumbnail": "https://books.google.com/small.jpg",
                },
                "infoLink": "https://books.google.com/books?id=abc123",
            },
        }
        result = _parse_volume(item)
        self.assertEqual(result["external_id"], "abc123")
        self.assertEqual(result["title"], "Project Hail Mary")
        self.assertEqual(result["author"], "Andy Weir")
        self.assertEqual(result["cover_image_url"], "https://books.google.com/thumb.jpg")
        self.assertEqual(result["description"], "An astronaut\n\nsaves Earth.")
        self.assertEqual(result["publication_date"], "2021-01-01")
        self.assertEqual(result["isbn"], "9780593135204")
        self.assertEqual(result["publisher"], "Ballantine Books")
        self.assertEqual(result["page_count"], 476)
        self.assertEqual(result["genres"], "Science fiction")
        self.assertIsNone(result["series"])
        self.assertEqual(result["catalogue_url"], "https://books.google.com/books?id=abc123")

    def test_tolerates_missing_volume_info_fields(self) -> None:
        item = {"id": "xyz", "volumeInfo": {"title": "Untitled"}}
        result = _parse_volume(item)
        self.assertEqual(result["title"], "Untitled")
        self.assertIsNone(result["author"])
        self.assertIsNone(result["cover_image_url"])
        self.assertIsNone(result["description"])
        self.assertIsNone(result["publication_date"])
        self.assertIsNone(result["isbn"])
        self.assertIsNone(result["publisher"])
        self.assertIsNone(result["page_count"])
        self.assertIsNone(result["genres"])
        self.assertIsNone(result["catalogue_url"])

    def test_falls_back_to_canonical_volume_link(self) -> None:
        item = {
            "id": "xyz",
            "volumeInfo": {
                "title": "Untitled",
                "canonicalVolumeLink": "https://books.google.com/books/about/Untitled.html",
            },
        }
        result = _parse_volume(item)
        self.assertEqual(
            result["catalogue_url"],
            "https://books.google.com/books/about/Untitled.html",
        )


class CatalogueSearchTests(unittest.TestCase):
    def test_rejects_a_blank_query(self) -> None:
        with self.assertRaises(CatalogueImportError):
            search_catalogue_books("   ")

    @patch("bookclub.catalogue.httpx.get")
    def test_returns_parsed_results_and_skips_untitled_items(self, get) -> None:
        get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "items": [
                    {"id": "1", "volumeInfo": {"title": "Eversion"}},
                    {"id": "2", "volumeInfo": {}},
                    None,
                ]
            },
        )
        get.return_value.raise_for_status = lambda: None
        results = search_catalogue_books("Eversion")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Eversion")

    @patch("bookclub.catalogue.httpx.get")
    def test_returns_empty_list_when_no_items(self, get) -> None:
        get.return_value = Mock(status_code=200, json=lambda: {})
        get.return_value.raise_for_status = lambda: None
        self.assertEqual(search_catalogue_books("no such book"), [])

    @patch("bookclub.catalogue.httpx.get")
    def test_wraps_http_errors(self, get) -> None:
        get.side_effect = httpx.ConnectError("boom")
        with self.assertRaises(CatalogueImportError):
            search_catalogue_books("Eversion")

    @patch("bookclub.catalogue.httpx.get")
    def test_wraps_non_2xx_responses(self, get) -> None:
        response = Mock(status_code=500)
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "server error", request=Mock(), response=response
        )
        get.return_value = response
        with self.assertRaises(CatalogueImportError):
            search_catalogue_books("Eversion")


if __name__ == "__main__":
    unittest.main()
