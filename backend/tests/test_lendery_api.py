import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, migrate_existing_database
from accounts.models import LibtoolsUser
from lendery.availability import AvailabilityCheckError, AvailabilityResult
from lendery.component_images import component_image_path
from lendery.models import ItemActivity
from lendery.routes import get_db
from main import app
from security import hash_password


def _availability_payload(*entries: dict) -> dict:
    return {
        "availability": {
            "metadataId": "S130C603511",
            "errorClassification": None,
        },
        "entities": {
            "bibItems": {
                str(index): entry for index, entry in enumerate(entries)
            },
            "availabilities": {"S130C603511": {"statusType": "AVAILABLE"}},
        },
    }


def _bib_item(barcode: str, status_type: str, status: str) -> dict:
    return {
        "itemId": f"603511|{barcode}||1",
        "branch": {"code": "9", "name": "Pierre Berton Resource Library"},
        "availability": {"status": status, "statusType": status_type},
    }


class LenderyAvailabilityApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            expire_on_commit=False,
        )

        def override_get_db():
            db: Session = cls.sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        self.upload_directory = tempfile.TemporaryDirectory()
        self.upload_environment = patch.dict(
            os.environ,
            {"LIBTOOLS_UPLOAD_DIR": self.upload_directory.name},
        )
        self.upload_environment.start()
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        with self.sessions() as db:
            user = LibtoolsUser(
                    name="Admin",
                    username="admin",
                    password_hash=hash_password("admin-password"),
                    role="admin",
            )
            db.add(user)
            db.commit()
        response = self.client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "admin-password",
            },
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self) -> None:
        self.upload_environment.stop()
        self.upload_directory.cleanup()

    @staticmethod
    def sample_png(width: int = 1800, height: int = 900) -> bytes:
        contents = BytesIO()
        Image.new("RGB", (width, height), (42, 112, 83)).save(
            contents,
            format="PNG",
        )
        return contents.getvalue()

    @staticmethod
    def sample_heif() -> bytes:
        contents = BytesIO()
        Image.new("RGB", (120, 80), (218, 170, 86)).save(
            contents,
            format="HEIF",
        )
        return contents.getvalue()

    def create_linked_item(self, barcode: str = "LENDERY-1") -> dict:
        with patch(
            "lendery.availability.check_availability",
            return_value=AvailabilityResult("available", 1, 1),
        ):
            response = self.client.post(
                "/lendery/items",
                json={
                    "name": "Carpet cleaner",
                    "barcode": barcode,
                    "library_url": (
                        "https://vaughanpl.bibliocommons.com/"
                        "v2/record/S130C603511"
                    ),
                },
            )
        self.assertEqual(response.status_code, 201)
        return response.json()

    @patch("lendery.availability.check_availability")
    def test_creating_a_linked_item_checks_availability_immediately(
        self, check
    ) -> None:
        check.return_value = AvailabilityResult("checked_out", 0, 1)

        response = self.client.post(
            "/lendery/items",
            json={
                "name": "Carpet cleaner",
                "barcode": "IMMEDIATE-1",
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/"
                    "v2/record/S130C603511"
                ),
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertEqual(created["availability_status"], "checked_out")
        self.assertEqual(created["available_copies"], 0)
        self.assertIsNotNone(created["availability_checked_at"])
        check.assert_called_once()

    @patch("lendery.availability.check_availability")
    def test_changing_the_library_url_checks_availability_immediately(
        self, check
    ) -> None:
        check.return_value = AvailabilityResult("available", 1, 1)
        created = self.create_linked_item()
        check.reset_mock()

        check.return_value = AvailabilityResult("not_held", 0, 0)
        response = self.client.patch(
            f"/lendery/items/{created['id']}",
            json={
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/"
                    "v2/record/S130C999999"
                ),
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["availability_status"], "not_held")
        check.assert_called_once()

    @staticmethod
    def _catalogue_item_fixture() -> dict:
        return {
            "name": "ThermoMaven 3000FT Smart Wireless Meat Thermometer",
            "description": "Monitor food from up to 3000 feet away.",
            "image_url": (
                "https://www.vaughanpl.info/img/catalogue/lendery/MeatThermo.jpg"
            ),
            "manual_url": (
                "https://www.vaughanpl.info/files/catalogue/"
                "ThermoMaven_X2_User_Manual_1.0.pdf"
            ),
            "library_url": (
                "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
            ),
        }

    @patch("lendery.availability.fetch_availability_payload")
    @patch("lendery.catalogue.fetch_catalogue_item")
    def test_imports_item_details_from_vaughan_catalogue(
        self, fetch_item, fetch_availability
    ) -> None:
        fetch_item.return_value = self._catalogue_item_fixture()
        fetch_availability.return_value = _availability_payload(
            _bib_item("33288098578375", "AVAILABLE", "AVAILABLE"),
        )
        response = self.client.post(
            "/lendery/items/import",
            json={
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["name"],
            "ThermoMaven 3000FT Smart Wireless Meat Thermometer",
        )
        self.assertTrue(response.json()["manual_url"].endswith(".pdf"))
        self.assertEqual(response.json()["barcode"], "33288098578375")
        fetch_item.assert_called_once_with(
            "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
        )

    @patch("lendery.availability.fetch_availability_payload")
    @patch("lendery.catalogue.fetch_catalogue_item")
    def test_import_leaves_barcode_blank_when_multiple_copies_are_untracked(
        self, fetch_item, fetch_availability
    ) -> None:
        fetch_item.return_value = self._catalogue_item_fixture()
        fetch_availability.return_value = _availability_payload(
            _bib_item("BARCODE-A", "AVAILABLE", "AVAILABLE"),
            _bib_item("BARCODE-B", "UNAVAILABLE", "CHECKED_OUT"),
        )
        response = self.client.post(
            "/lendery/items/import",
            json={
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["barcode"])

    @patch("lendery.availability.fetch_availability_payload")
    @patch("lendery.catalogue.fetch_catalogue_item")
    def test_import_leaves_barcode_blank_when_the_candidate_is_already_tracked(
        self, fetch_item, fetch_availability
    ) -> None:
        self.create_linked_item("33288098578375")
        fetch_item.return_value = self._catalogue_item_fixture()
        fetch_availability.return_value = _availability_payload(
            _bib_item("33288098578375", "AVAILABLE", "AVAILABLE"),
        )
        response = self.client.post(
            "/lendery/items/import",
            json={
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["barcode"])

    @patch("lendery.availability.fetch_availability_payload")
    @patch("lendery.catalogue.fetch_catalogue_item")
    def test_import_succeeds_without_a_barcode_suggestion_when_availability_check_fails(
        self, fetch_item, fetch_availability
    ) -> None:
        fetch_item.return_value = self._catalogue_item_fixture()
        fetch_availability.side_effect = AvailabilityCheckError("boom")
        response = self.client.post(
            "/lendery/items/import",
            json={
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["name"],
            "ThermoMaven 3000FT Smart Wireless Meat Thermometer",
        )
        self.assertIsNone(response.json()["barcode"])

    def test_lendery_page_uses_current_autofill_assets(self) -> None:
        response = self.client.get("/lendery")
        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/lendery.js?v=35', response.text)
        self.assertIn('/static/lendery.css?v=37', response.text)
        self.assertIn('<option value="alphabetical">Alphabetical</option>', response.text)
        self.assertIn('value="recently-active">Most recently used', response.text)
        self.assertIn('value="recently-added">Recently added', response.text)
        self.assertIn('class="dashboard-link" href="/dashboard"', response.text)
        self.assertIn('class="mobile-return-top" href="#lendery-top"', response.text)
        self.assertIn('href="/signup">Create an account</a>', response.text)
        self.assertIn('id="lendery-home"', response.text)
        self.assertIn('id="total-items-stat"', response.text)
        self.assertIn('id="suggestion-form"', response.text)
        self.assertIn('id="suggestions-dialog"', response.text)
        self.assertIn('href="/lendery/export"', response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

        export_page = self.client.get("/lendery/export")
        self.assertEqual(export_page.status_code, 200)
        self.assertIn('id="export-form"', export_page.text)
        self.assertIn("Item history", export_page.text)
        self.assertEqual(export_page.headers["cache-control"], "no-store")

    def test_removed_item_is_preserved_and_can_be_restored(self) -> None:
        item = self.create_linked_item("REMOVAL-1")

        missing_reason = self.client.post(
            f"/lendery/items/{item['id']}/remove",
            json={"reason": "   "},
        )
        self.assertEqual(missing_reason.status_code, 422, missing_reason.text)

        removed = self.client.post(
            f"/lendery/items/{item['id']}/remove",
            json={"reason": "Motor cannot be repaired"},
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(self.client.get("/lendery/items").json(), [])

        removed_items = self.client.get(
            "/lendery/items?lifecycle=removed"
        ).json()
        self.assertEqual(len(removed_items), 1)
        self.assertEqual(removed_items[0]["id"], item["id"])
        self.assertEqual(
            removed_items[0]["lifecycle_note"], "Motor cannot be repaired"
        )

        restored = self.client.post(f"/lendery/items/{item['id']}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["lifecycle_status"], "active")
        self.assertEqual(len(self.client.get("/lendery/items").json()), 1)

    def test_component_activity_updates_item_activity_time(self) -> None:
        item = self.create_linked_item("ACTIVITY-1")

        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Charging cable", "quantity": 1},
        )
        refreshed = self.client.get(f"/lendery/items/{item['id']}")

        self.assertEqual(component.status_code, 201, component.text)
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertNotEqual(refreshed.json()["updated_at"], item["updated_at"])

    def test_lifecycle_filters_keep_removed_items_out_of_inventory(self) -> None:
        active = self.create_linked_item("ACTIVE-1")
        removed = self.create_linked_item("REMOVED-1")
        self.client.post(
            f"/lendery/items/{removed['id']}/remove",
            json={"reason": "Withdrawn from the collection"},
        )

        inventory = self.client.get("/lendery/items").json()
        removed_items = self.client.get(
            "/lendery/items?lifecycle=removed"
        ).json()
        all_items = self.client.get("/lendery/items?lifecycle=all").json()

        self.assertEqual([entry["id"] for entry in inventory], [active["id"]])
        self.assertEqual([entry["id"] for entry in removed_items], [removed["id"]])
        self.assertEqual(len(all_items), 2)

    def test_existing_sqlite_items_receive_lifecycle_columns(self) -> None:
        legacy_engine = create_engine("sqlite://", poolclass=StaticPool)
        try:
            with legacy_engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE lendery_items ("
                        "id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, "
                        "lifecycle_status VARCHAR(20) NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO lendery_items "
                        "(id, name, lifecycle_status) "
                        "VALUES (1, 'Legacy drill', 'retired')"
                    )
                )

            with patch("database.engine", legacy_engine):
                migrate_existing_database()

            columns = {
                column["name"]
                for column in inspect(legacy_engine).get_columns(
                    "lendery_items"
                )
            }
            self.assertIn("lifecycle_status", columns)
            self.assertIn("lifecycle_changed_at", columns)
            with legacy_engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT lifecycle_status, lifecycle_changed_at "
                        "FROM lendery_items WHERE id = 1"
                    )
                ).one()
            self.assertEqual(row.lifecycle_status, "active")
            self.assertIsNotNone(row.lifecycle_changed_at)
        finally:
            legacy_engine.dispose()

    def test_existing_item_status_is_backfilled_into_activity_history(self) -> None:
        legacy_engine = create_engine("sqlite://", poolclass=StaticPool)
        try:
            with legacy_engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE lendery_items ("
                        "id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, "
                        "barcode VARCHAR(50) NOT NULL, category VARCHAR(100), "
                        "lifecycle_status VARCHAR(20) NOT NULL, lifecycle_note TEXT, "
                        "lifecycle_changed_at TIMESTAMP, created_at TIMESTAMP, "
                        "updated_at TIMESTAMP)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO lendery_items "
                        "(id, name, barcode, category, lifecycle_status, lifecycle_note, "
                        "lifecycle_changed_at, created_at, updated_at) VALUES "
                        "(1, 'Legacy drill', 'LEGACY-1', 'Tools', 'removed', "
                        "'Could not be repaired', CURRENT_TIMESTAMP, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
            ItemActivity.__table__.create(bind=legacy_engine)

            with patch("database.engine", legacy_engine):
                migrate_existing_database()
                migrate_existing_database()

            with legacy_engine.connect() as connection:
                rows = connection.execute(
                    text(
                        "SELECT event_type, reason FROM lendery_item_activity "
                        "ORDER BY id"
                    )
                ).all()
            self.assertEqual(
                rows,
                [
                    ("item_added", "Existing inventory record"),
                    ("removed_from_collection", "Could not be repaired"),
                ],
            )
        finally:
            legacy_engine.dispose()

    def test_only_removed_items_can_be_permanently_deleted(self) -> None:
        item = self.create_linked_item("DELETE-FOREVER-1")
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Power cord", "quantity": 1},
        ).json()
        self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={
                "image": ("cord.png", self.sample_png(100, 100), "image/png")
            },
        )
        image_path = component_image_path(component["id"])
        self.assertTrue(image_path.exists())

        rejected = self.client.delete(
            f"/lendery/items/{item['id']}/permanent"
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)

        self.client.post(
            f"/lendery/items/{item['id']}/remove",
            json={"reason": "Duplicate record"},
        )
        deleted = self.client.delete(
            f"/lendery/items/{item['id']}/permanent"
        )

        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(
            self.client.get(f"/lendery/items/{item['id']}").status_code,
            404,
        )
        self.assertFalse(image_path.exists())

    @patch("lendery.availability.check_availability")
    def test_item_detail_refreshes_availability(self, check) -> None:
        check.return_value = AvailabilityResult(
            status="available",
            available_copies=1,
            total_copies_at_branch=2,
        )
        created = self.create_linked_item()

        response = self.client.get(
            f"/lendery/items/{created['id']}"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["availability_status"], "available")
        self.assertEqual(body["availability_status_version"], 2)
        self.assertEqual(body["available_copies"], 1)
        self.assertEqual(body["total_copies_at_branch"], 2)
        self.assertIsNotNone(body["availability_checked_at"])

    def test_in_and_out_filters_use_saved_status(self) -> None:
        created_in = self.create_linked_item("IN-1")
        created_out = self.create_linked_item("OUT-1")
        created_unavailable = self.create_linked_item("UNAVAILABLE-1")

        # One shared title-level BiblioCommons payload, as in the real
        # duplicate-copy case: all three Lendery rows point at the same
        # library_url/bib, but each bibItems entry carries a different
        # physical barcode, so each item must resolve to its own status.
        shared_payload = _availability_payload(
            _bib_item("IN-1", "AVAILABLE", "AVAILABLE"),
            _bib_item("OUT-1", "UNAVAILABLE", "CHECKED_OUT"),
            _bib_item("UNAVAILABLE-1", "UNAVAILABLE", "DAMAGED"),
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=shared_payload)

        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch(
            "lendery.availability._default_client",
            return_value=mock_client,
        ):
            self.client.get(f"/lendery/items/{created_in['id']}")
            self.client.get(f"/lendery/items/{created_out['id']}")
            self.client.get(f"/lendery/items/{created_unavailable['id']}")

        in_items = self.client.get(
            "/lendery/items?availability=in"
        ).json()
        out_items = self.client.get(
            "/lendery/items?availability=out"
        ).json()
        unavailable_items = self.client.get(
            "/lendery/items?availability=unavailable"
        ).json()

        self.assertEqual(
            [entry["barcode"] for entry in in_items],
            ["IN-1"],
        )
        self.assertEqual(
            [entry["barcode"] for entry in out_items],
            ["OUT-1"],
        )
        self.assertEqual(
            [entry["barcode"] for entry in unavailable_items],
            ["UNAVAILABLE-1"],
        )

    def test_export_csv_lists_inventory_and_requires_manage_access(self) -> None:
        self.create_linked_item("EXPORT-1")

        response = self.client.get("/lendery/items/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith("text/csv")
        )
        rows = response.text.splitlines()
        self.assertIn("barcode", rows[0])
        self.assertTrue(any("EXPORT-1" in row for row in rows[1:]))

    def test_configurable_inventory_and_activity_exports(self) -> None:
        first = self.client.post(
            "/lendery/items",
            json={"name": "Kitchen scale", "barcode": "EXPORT-A", "category": "Kitchen"},
        ).json()
        self.client.post(
            "/lendery/items",
            json={"name": "Cordless drill", "barcode": "EXPORT-B", "category": "Tools"},
        )

        options = self.client.get("/lendery/export/options")
        self.assertEqual(options.status_code, 200, options.text)
        self.assertEqual(options.json()["categories"], ["Kitchen", "Tools"])
        self.assertTrue(
            any(field["key"] == "barcode" for field in options.json()["inventory_fields"])
        )

        inventory = self.client.post(
            "/lendery/export/inventory.csv",
            json={
                "fields": ["barcode", "name"],
                "scope": "category",
                "category": "Kitchen",
                "include_removed": True,
            },
        )
        self.assertEqual(inventory.status_code, 200, inventory.text)
        self.assertEqual(inventory.text.splitlines()[0], "barcode,name")
        self.assertIn("EXPORT-A", inventory.text)
        self.assertNotIn("EXPORT-B", inventory.text)

        activity = self.client.post(
            "/lendery/export/activity.csv",
            json={
                "fields": ["event_type", "barcode", "item_name"],
                "scope": "item",
                "item_id": first["id"],
            },
        )
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertEqual(
            activity.text.splitlines()[0], "event_type,barcode,item_name"
        )
        self.assertIn("item_added,EXPORT-A,Kitchen scale", activity.text)
        self.assertNotIn("EXPORT-B", activity.text)

    def test_operational_history_tracks_unavailable_return_and_survives_deletion(
        self,
    ) -> None:
        item = self.client.post(
            "/lendery/items",
            json={"name": "Button maker", "barcode": "HISTORY-1", "category": "Crafts"},
        ).json()

        unavailable = self.client.post(
            f"/lendery/items/{item['id']}/unavailable",
            json={"reason": "Handle is cracked"},
        )
        self.assertEqual(unavailable.status_code, 200, unavailable.text)
        self.assertEqual(unavailable.json()["lifecycle_status"], "unavailable")
        self.assertEqual(unavailable.json()["lifecycle_note"], "Handle is cracked")

        returned = self.client.post(
            f"/lendery/items/{item['id']}/restore",
            json={"note": "Replacement handle installed"},
        )
        self.assertEqual(returned.status_code, 200, returned.text)
        self.assertEqual(returned.json()["lifecycle_status"], "active")
        self.assertIsNone(returned.json()["lifecycle_note"])

        removed = self.client.post(
            f"/lendery/items/{item['id']}/remove",
            json={"reason": "Withdrawn after repeated failures"},
        )
        self.assertEqual(removed.status_code, 200, removed.text)

        history = self.client.get(f"/lendery/items/{item['id']}/activity")
        self.assertEqual(history.status_code, 200, history.text)
        event_types = [entry["event_type"] for entry in history.json()]
        self.assertEqual(
            event_types,
            [
                "removed_from_collection",
                "returned_to_circulation",
                "marked_unavailable",
                "item_added",
            ],
        )
        self.assertEqual(history.json()[2]["reason"], "Handle is cracked")

        deleted = self.client.delete(f"/lendery/items/{item['id']}/permanent")
        self.assertEqual(deleted.status_code, 204, deleted.text)
        global_history = self.client.get(f"/lendery/activity?item_id={item['id']}")
        self.assertEqual(global_history.status_code, 200, global_history.text)
        self.assertEqual(global_history.json()[0]["event_type"], "permanently_deleted")
        self.assertTrue(
            all(entry["item_id"] is None for entry in global_history.json())
        )
        options = self.client.get("/lendery/export/options").json()
        self.assertNotIn(item["id"], [entry["id"] for entry in options["items"]])
        self.assertNotIn("Crafts", options["categories"])
        self.assertIn("Crafts", options["activity_categories"])
        self.assertIn(
            item["id"], [entry["id"] for entry in options["activity_items"]]
        )
        deleted_item_export = self.client.post(
            "/lendery/export/activity.csv",
            json={
                "fields": ["event_type", "barcode", "item_name"],
                "scope": "item",
                "item_id": item["id"],
            },
        )
        self.assertEqual(deleted_item_export.status_code, 200)
        self.assertIn("HISTORY-1", deleted_item_export.text)

    def test_maintenance_orders_and_repairs_are_added_to_item_history(self) -> None:
        item = self.client.post(
            "/lendery/items",
            json={"name": "Projector", "barcode": "REPAIR-HISTORY"},
        ).json()
        repair_case = self.client.post(
            f"/lendery/items/{item['id']}/maintenance",
            json={"title": "Fan is noisy", "description": "Rattles during use"},
        ).json()
        self.client.post(
            f"/lendery/maintenance/{repair_case['id']}/events",
            json={
                "event_type": "part_ordered",
                "part_name": "Cooling fan",
                "quantity": 1,
                "cost": "19.50",
                "order_number": "PO-99",
            },
        )
        self.client.post(
            f"/lendery/maintenance/{repair_case['id']}/events",
            json={"event_type": "repair_completed", "note": "Fan replaced and tested"},
        )

        history = self.client.get(f"/lendery/items/{item['id']}/activity").json()
        self.assertEqual(
            [entry["event_type"] for entry in history[:3]],
            ["repair_completed", "part_ordered", "maintenance_opened"],
        )
        ordered = history[1]
        self.assertEqual(ordered["part_name"], "Cooling fan")
        self.assertEqual(ordered["quantity"], 1)
        self.assertEqual(ordered["order_number"], "PO-99")
        self.assertEqual(ordered["cost"], "19.50")

    def test_physical_manual_inclusion_and_missing_flag_are_tracked(self) -> None:
        response = self.client.post(
            "/lendery/items",
            json={
                "name": "Telescope",
                "barcode": "MANUAL-1",
                "physical_manual_included": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertTrue(created["physical_manual_included"])
        self.assertFalse(created["physical_manual_missing"])

        default_response = self.client.post(
            "/lendery/items",
            json={"name": "Sewing kit", "barcode": "MANUAL-2"},
        )
        self.assertEqual(default_response.status_code, 201, default_response.text)
        self.assertFalse(default_response.json()["physical_manual_included"])

        flagged = self.client.patch(
            f"/lendery/items/{created['id']}",
            json={"physical_manual_missing": True},
        )
        self.assertEqual(flagged.status_code, 200, flagged.text)
        self.assertTrue(flagged.json()["physical_manual_missing"])

        unflagged = self.client.patch(
            f"/lendery/items/{created['id']}",
            json={"physical_manual_missing": False},
        )
        self.assertEqual(unflagged.status_code, 200, unflagged.text)
        self.assertFalse(unflagged.json()["physical_manual_missing"])

        csv_rows = self.client.get(
            "/lendery/items/export.csv"
        ).text.splitlines()
        self.assertIn("physical_manual_included", csv_rows[0])
        self.assertTrue(
            any("MANUAL-1" in row and "True" in row for row in csv_rows[1:])
        )

        with self.sessions() as db:
            viewer = LibtoolsUser(
                name="Viewer",
                username="viewer",
                password_hash=hash_password("viewer-password"),
                role="user",
            )
            db.add(viewer)
            db.commit()

        viewer_client = TestClient(app)
        login = viewer_client.post(
            "/auth/login",
            json={"username": "viewer", "password": "viewer-password"},
        )
        self.assertEqual(login.status_code, 200)
        forbidden = viewer_client.get("/lendery/items/export.csv")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(
            viewer_client.get("/lendery/export/options").status_code, 403
        )
        self.assertEqual(viewer_client.get("/lendery/activity").status_code, 403)
        self.assertEqual(
            viewer_client.post(
                "/lendery/export/activity.csv",
                json={"fields": ["event_type"], "scope": "all"},
            ).status_code,
            403,
        )
        viewer_client.close()

    def test_component_photo_upload_is_processed_and_served(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Upholstery nozzle", "quantity": 1},
        ).json()

        uploaded = self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={
                "image": ("nozzle.png", self.sample_png(), "image/png"),
            },
        )

        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(
            uploaded.json()["image_url"],
            f"/lendery/components/{component['id']}/image",
        )
        saved_path = component_image_path(component["id"])
        self.assertTrue(saved_path.is_file())
        with Image.open(saved_path) as processed:
            self.assertEqual(processed.format, "WEBP")
            self.assertEqual(processed.size, (1200, 600))

        served = self.client.get(uploaded.json()["image_url"])
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.headers["content-type"], "image/webp")
        self.assertEqual(served.headers["cache-control"], "private, no-store")

    def test_invalid_component_photo_is_rejected(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Hose", "quantity": 1},
        ).json()

        response = self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={"image": ("not-an-image.jpg", b"hello", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(component_image_path(component["id"]).exists())

    def test_iphone_heif_photo_is_supported(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Power cord", "quantity": 1},
        ).json()

        response = self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={"image": ("cord.heic", self.sample_heif(), "image/heic")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        with Image.open(component_image_path(component["id"])) as processed:
            self.assertEqual(processed.format, "WEBP")

    def test_component_photo_is_removed_with_component(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Brush", "quantity": 1},
        ).json()
        self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={"image": ("brush.png", self.sample_png(100, 100), "image/png")},
        )
        self.assertTrue(component_image_path(component["id"]).exists())

        deleted = self.client.delete(
            f"/lendery/components/{component['id']}"
        )

        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(component_image_path(component["id"]).exists())

    def test_removing_component_photo_clears_reference(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Crevice tool", "quantity": 1},
        ).json()
        self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={"image": ("tool.png", self.sample_png(100, 100), "image/png")},
        )

        removed = self.client.delete(
            f"/lendery/components/{component['id']}/image"
        )
        refreshed = self.client.get(
            f"/lendery/components/{component['id']}"
        )

        self.assertEqual(removed.status_code, 204)
        self.assertIsNone(refreshed.json()["image_url"])
        self.assertFalse(component_image_path(component["id"]).exists())

    def test_public_barcode_lookup_requires_no_auth_and_hides_staff_fields(
        self,
    ) -> None:
        item = self.client.post(
            "/lendery/items",
            json={
                "name": "Carpet cleaner",
                "barcode": "PUBLIC-1",
                "notes": "Staff-only note",
                "purchase_price": 199.99,
                "purchase_url": "https://vendor.example.com/carpet-cleaner",
                "category": "Cleaning",
            },
        ).json()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={
                "name": "Hose attachment",
                "quantity": 1,
                "check_in_notes": "Staff-only check-in note",
            },
        ).json()
        self.client.post(
            f"/lendery/components/{component['id']}/missing-report",
            json={"note": "Reported missing by a staff member"},
        )

        anonymous = TestClient(app)
        try:
            response = anonymous.get(
                f"/api/public/lendery/items/barcode/{item['barcode']}"
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()

            self.assertEqual(body["name"], "Carpet cleaner")
            self.assertEqual(body["barcode"], "PUBLIC-1")
            self.assertEqual(body["category"], "Cleaning")
            self.assertEqual(len(body["components"]), 1)
            self.assertEqual(body["components"][0]["name"], "Hose attachment")

            for leaked_field in (
                "id",
                "notes",
                "purchase_price",
                "purchase_url",
                "lifecycle_note",
                "availability_status",
                "availability_error",
                "library_url",
            ):
                self.assertNotIn(leaked_field, body)
            for leaked_component_field in (
                "id",
                "check_in_notes",
                "missing_reported_at",
                "missing_reported_by",
                "missing_note",
            ):
                self.assertNotIn(leaked_component_field, body["components"][0])
        finally:
            anonymous.close()

    def test_public_barcode_lookup_404s_for_unknown_and_removed_items(
        self,
    ) -> None:
        item = self.create_linked_item(barcode="PUBLIC-2")
        self.client.post(
            f"/lendery/items/{item['id']}/remove",
            json={"reason": "Retired"},
        )

        anonymous = TestClient(app)
        try:
            missing = anonymous.get(
                "/api/public/lendery/items/barcode/does-not-exist"
            )
            self.assertEqual(missing.status_code, 404)

            removed = anonymous.get(
                f"/api/public/lendery/items/barcode/{item['barcode']}"
            )
            self.assertEqual(removed.status_code, 404)
        finally:
            anonymous.close()


if __name__ == "__main__":
    unittest.main()
