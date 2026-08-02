import json
import unittest

from lendery.catalogue import parse_catalogue_item


class LenderyCatalogueTests(unittest.TestCase):
    @staticmethod
    def catalogue_page(state: dict) -> str:
        return (
            '<script type="application/json" data-iso-key="_0">'
            + json.dumps(state)
            + "</script>"
        )

    def test_parses_item_and_primary_online_resource(self) -> None:
        record_id = "S130C772570"
        state = {
            "entities": {
                "catalogBibs": {
                    record_id: {
                        "brief": {
                            "title": (
                                "ThermoMaven 3000FT Smart Wireless Meat Thermometer"
                            ),
                            "description": "Monitor food from up to 3000 feet away.",
                            "coverImage": {
                                "large": (
                                    "https://www.vaughanpl.info/img/catalogue/"
                                    "lendery/MeatThermo.jpg"
                                )
                            },
                        },
                        "fields": [],
                    }
                },
                "bibs": {
                    record_id: {
                        "availability": {
                            "eresourceUrl": (
                                "https://www.vaughanpl.info/files/catalogue/"
                                "ThermoMaven_X2_User_Manual_1.0.pdf"
                            )
                        }
                    }
                },
            }
        }
        page = self.catalogue_page(state)

        result = parse_catalogue_item(
            page,
            "https://vaughanpl.bibliocommons.com/v2/record/S130C772570",
            record_id,
        )

        self.assertEqual(
            result["name"],
            "ThermoMaven 3000FT Smart Wireless Meat Thermometer",
        )
        self.assertEqual(
            result["manual_url"],
            "https://www.vaughanpl.info/files/catalogue/"
            "ThermoMaven_X2_User_Manual_1.0.pdf",
        )
        self.assertTrue(result["image_url"].endswith("MeatThermo.jpg"))

    def test_missing_manual_is_valid(self) -> None:
        record_id = "S130C700001"
        state = {
            "entities": {
                "catalogBibs": {
                    record_id: {
                        "brief": {
                            "title": "Portable tool",
                            "description": "A useful item.",
                            "coverImage": {
                                "large": "https://www.vaughanpl.info/item.jpg"
                            },
                        },
                        "fields": [],
                    }
                },
                "bibs": {record_id: {"availability": {}}},
            }
        }

        result = parse_catalogue_item(
            self.catalogue_page(state),
            f"https://vaughanpl.bibliocommons.com/v2/record/{record_id}",
            record_id,
        )

        self.assertEqual(result["name"], "Portable tool")
        self.assertIsNone(result["manual_url"])


if __name__ == "__main__":
    unittest.main()
