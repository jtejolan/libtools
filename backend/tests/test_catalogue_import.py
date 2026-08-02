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
