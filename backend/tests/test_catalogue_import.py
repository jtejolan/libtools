import json
import unittest

from bookclub.catalogue import (
    CatalogueImportError,
    _validated_url,
    parse_catalogue_record,
)


class CatalogueImportTests(unittest.TestCase):
    def test_parses_bibliocommons_embedded_metadata(self) -> None:
        record = {
            "brief": {
                "title": "Project Hail Mary",
                "creators": [{"fullName": "Weir, Andy"}],
                "coverImage": {"large": "https://www.syndetics.com/cover.jpg"},
                "description": "An astronaut&lt;br /&gt;&lt;br /&gt;saves Earth.",
                "publicationDate": "2021",
            },
            "fields": [
                {
                    "items": [
                        {
                            "fieldName": "PUBLICATION",
                            "fieldValues": [
                                {"primary": {"values": ["New York : Ballantine Books, [2021]"]}}
                            ],
                        },
                        {
                            "fieldName": "DESCRIPTION",
                            "fieldValues": [{"primary": {"values": ["476 pages : illustrations"]}}],
                        },
                    ]
                },
                {
                    "items": [
                        {
                            "fieldName": "ISBN",
                            "fieldValues": [
                                {"primary": {"values": ["0593135202"]}},
                                {"primary": {"values": ["9780593135204"]}},
                            ],
                        },
                        {
                            "fieldName": "GENRE",
                            "fieldValues": [{"primary": {"values": ["Science fiction."]}}],
                        },
                        {
                            "fieldName": "SUBJECT",
                            "fieldValues": [{"primary": {"values": ["Astronauts — Fiction."]}}],
                        },
                    ]
                },
            ],
        }
        state = {"entities": {"catalogBibs": {"S130C532272": record}}}
        page = (
            '<script type="application/json" data-iso-key="_0">'
            + json.dumps(state)
            + "</script>"
        )
        result = parse_catalogue_record(
            page,
            "https://vaughanpl.bibliocommons.com/v2/record/S130C532272",
            "S130C532272",
        )
        self.assertEqual(result["title"], "Project Hail Mary")
        self.assertEqual(result["author"], "Andy Weir")
        self.assertEqual(result["isbn"], "9780593135204")
        self.assertEqual(result["publisher"], "Ballantine Books")
        self.assertEqual(result["page_count"], 476)
        self.assertEqual(result["publication_date"], "2021-01-01")
        self.assertEqual(result["description"], "An astronaut\n\nsaves Earth.")

    def test_tolerates_explicit_nulls_in_bibliocommons_response(self) -> None:
        # BiblioCommons sometimes serializes empty relations as explicit
        # JSON nulls rather than omitting the key; dict.get(key, default)
        # doesn't fall back to `default` in that case, so these must not
        # raise anything but CatalogueImportError-safe results.
        record = {
            "brief": {
                "title": "Untitled Record",
                "creators": None,
                "coverImage": None,
                "isbns": None,
            },
            "fields": [
                {
                    "items": [
                        {
                            "fieldName": "ISBN",
                            "fieldValues": [{"primary": None}],
                        },
                        {
                            "fieldName": "GENRE",
                            "fieldValues": None,
                        },
                    ]
                },
                None,
            ],
        }
        state = {"entities": {"catalogBibs": {"S130C1": record}}}
        page = (
            '<script type="application/json" data-iso-key="_0">'
            + json.dumps(state)
            + "</script>"
        )
        result = parse_catalogue_record(
            page,
            "https://vaughanpl.bibliocommons.com/v2/record/S130C1",
            "S130C1",
        )
        self.assertEqual(result["title"], "Untitled Record")
        self.assertIsNone(result["author"])
        self.assertIsNone(result["isbn"])
        self.assertIsNone(result["cover_image_url"])

    def test_raises_import_error_when_brief_is_null(self) -> None:
        state = {"entities": {"catalogBibs": {"S130C1": {"brief": None}}}}
        page = (
            '<script type="application/json" data-iso-key="_0">'
            + json.dumps(state)
            + "</script>"
        )
        with self.assertRaises(CatalogueImportError):
            parse_catalogue_record(
                page,
                "https://vaughanpl.bibliocommons.com/v2/record/S130C1",
                "S130C1",
            )

    def test_skips_null_entries_within_a_values_list(self) -> None:
        # Real BiblioCommons data seen in the wild: a SUBJECT heading that
        # failed to resolve comes back as {"values": [null]} - the list
        # itself is present, but one entry inside it is null.
        record = {
            "brief": {"title": "Eversion"},
            "fields": [
                {
                    "items": [
                        {
                            "fieldName": "SUBJECT",
                            "fieldValues": [
                                {"primary": {"values": ["Explorers — Fiction."]}},
                                {"primary": {"values": [None]}},
                            ],
                        },
                    ]
                },
            ],
        }
        state = {"entities": {"catalogBibs": {"S130C758565": record}}}
        page = (
            '<script type="application/json" data-iso-key="_0">'
            + json.dumps(state)
            + "</script>"
        )
        result = parse_catalogue_record(
            page,
            "https://vaughanpl.bibliocommons.com/v2/record/S130C758565",
            "S130C758565",
        )
        self.assertEqual(result["genres"], "Explorers — Fiction")

    def test_isbn_field_strips_marc_qualifier_and_price(self) -> None:
        # e.g. "9780316462822 (trade paperback) $25.99" - only the leading
        # token is the ISBN; naively stripping non-digits from the whole
        # string folds the price digits into the ISBN.
        record = {
            "brief": {"title": "Eversion"},
            "fields": [
                {
                    "items": [
                        {
                            "fieldName": "ISBN",
                            "fieldValues": [
                                {
                                    "primary": {
                                        "values": [
                                            "9780316462822 (trade paperback) $25.99"
                                        ]
                                    }
                                }
                            ],
                        },
                    ]
                },
            ],
        }
        state = {"entities": {"catalogBibs": {"S130C758565": record}}}
        page = (
            '<script type="application/json" data-iso-key="_0">'
            + json.dumps(state)
            + "</script>"
        )
        result = parse_catalogue_record(
            page,
            "https://vaughanpl.bibliocommons.com/v2/record/S130C758565",
            "S130C758565",
        )
        self.assertEqual(result["isbn"], "9780316462822")

    def test_rejects_non_vaughan_and_non_record_urls(self) -> None:
        for url in (
            "https://example.com/v2/record/S130C532272",
            "http://vaughanpl.bibliocommons.com/v2/record/S130C532272",
            "https://vaughanpl.bibliocommons.com/v2/search?query=books",
        ):
            with self.subTest(url=url), self.assertRaises(CatalogueImportError):
                _validated_url(url)


if __name__ == "__main__":
    unittest.main()
