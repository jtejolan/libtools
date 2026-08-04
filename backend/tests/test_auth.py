import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from accounts.models import LibtoolsUser, ToolAccess
from database import Base
from dependencies import get_db
from main import app
from security import hash_password


class LenderyAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(
            bind=cls.engine, autoflush=False, expire_on_commit=False
        )

        def override_get_db():
            db: Session = cls.sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        login_throttle.reset()
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        with self.sessions() as db:
            users = {
                "admin": LibtoolsUser(
                    name="Admin",
                    username="admin",
                    password_hash=hash_password("admin-password"),
                    role="admin",
                ),
                "manager": LibtoolsUser(
                    name="Manager",
                    username="manager",
                    password_hash=hash_password("manager-password"),
                    role="user",
                ),
                "viewer": LibtoolsUser(
                    name="Viewer",
                    username="viewer",
                    password_hash=hash_password("viewer-password"),
                    role="user",
                ),
                "other": LibtoolsUser(
                    name="Other",
                    username="other",
                    password_hash=hash_password("other-password"),
                    role="user",
                ),
            }
            db.add_all(users.values())
            db.flush()
            db.add_all(
                [
                    ToolAccess(
                        user_id=users["manager"].id,
                        tool_key="lendery_manage",
                    ),
                ]
            )
            db.commit()
        self.anonymous = TestClient(app)
        self.admin = self.logged_in("admin", "admin-password")
        self.manager = self.logged_in("manager", "manager-password")
        self.viewer = self.logged_in("viewer", "viewer-password")
        self.other = self.logged_in("other", "other-password")

    def tearDown(self) -> None:
        for client in (
            self.anonymous,
            self.admin,
            self.manager,
            self.viewer,
            self.other,
        ):
            client.close()

    def logged_in(self, username: str, password: str) -> TestClient:
        client = TestClient(app)
        response = client.post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return client

    def create_item(self) -> dict:
        response = self.manager.post(
            "/lendery/items",
            json={
                "name": "Projector kit",
                "barcode": "KIT-1",
                "components": [{"name": "Remote", "quantity": 1}],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_inventory_requires_a_personal_account(self) -> None:
        self.assertEqual(self.anonymous.get("/lendery/items").status_code, 401)
        self.assertEqual(self.other.get("/lendery/items").status_code, 200)

    def test_viewer_can_view_and_refresh(self) -> None:
        item = self.create_item()
        self.assertEqual(self.viewer.get("/lendery/items").status_code, 200)
        self.assertEqual(
            self.viewer.get(f"/lendery/items/{item['id']}").status_code,
            200,
        )
        self.assertEqual(
            self.viewer.post(
                f"/lendery/items/{item['id']}/availability/refresh"
            ).status_code,
            200,
        )

    def test_default_viewer_cannot_change_inventory(self) -> None:
        response = self.other.post(
            "/lendery/items",
            json={"name": "New item", "barcode": "NEW-1"},
        )
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_change_inventory(self) -> None:
        item = self.create_item()
        component_id = item["components"][0]["id"]
        attempts = [
            self.viewer.post(
                "/lendery/items",
                json={"name": "New item", "barcode": "NEW-1"},
            ),
            self.viewer.patch(
                f"/lendery/items/{item['id']}", json={"name": "Changed"}
            ),
            self.viewer.delete(f"/lendery/items/{item['id']}"),
            self.viewer.post(
                f"/lendery/items/{item['id']}/components",
                json={"name": "Cable", "quantity": 1},
            ),
            self.viewer.patch(
                f"/lendery/components/{component_id}", json={"name": "Changed"}
            ),
            self.viewer.post(
                f"/lendery/components/{component_id}/image",
                files={"image": ("photo.jpg", b"not-used", "image/jpeg")},
            ),
            self.viewer.delete(
                f"/lendery/components/{component_id}/image"
            ),
            self.viewer.delete(f"/lendery/components/{component_id}"),
        ]
        self.assertTrue(all(response.status_code == 403 for response in attempts))

    def test_manager_can_change_inventory_but_docs_need_platform_admin(self) -> None:
        item = self.create_item()
        changed = self.manager.patch(
            f"/lendery/items/{item['id']}", json={"name": "Updated kit"}
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.manager.get("/docs").status_code, 403)
        self.assertEqual(self.admin.get("/docs").status_code, 200)

    def test_maintenance_log_is_editor_only_and_tracks_repair_history(self) -> None:
        item = self.create_item()
        component_id = item["components"][0]["id"]

        self.assertEqual(
            self.viewer.get(
                f"/lendery/items/{item['id']}/maintenance"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.viewer.post(
                f"/lendery/items/{item['id']}/maintenance",
                json={"title": "Missing remote"},
            ).status_code,
            403,
        )

        created = self.manager.post(
            f"/lendery/items/{item['id']}/maintenance",
            json={
                "title": "Damaged remote",
                "description": "Buttons no longer respond.",
                "component_id": component_id,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        repair_case = created.json()
        self.assertEqual(repair_case["status"], "open")
        self.assertEqual(repair_case["component_name"], "Remote")

        ordered = self.manager.post(
            f"/lendery/maintenance/{repair_case['id']}/events",
            json={
                "event_type": "part_ordered",
                "note": "Ordered a replacement.",
                "part_name": "Replacement remote",
                "quantity": 1,
                "cost": "24.99",
                "vendor_url": "https://example.com/remote",
                "order_number": "PO-123",
            },
        )
        self.assertEqual(ordered.status_code, 201, ordered.text)
        self.assertEqual(ordered.json()["status"], "waiting_for_part")

        installed = self.manager.post(
            f"/lendery/maintenance/{repair_case['id']}/events",
            json={
                "event_type": "part_installed",
                "part_name": "Replacement remote",
                "note": "Added to the kit and tested.",
            },
        )
        self.assertEqual(installed.status_code, 201, installed.text)
        self.assertEqual(installed.json()["status"], "in_repair")

        completed = self.manager.post(
            f"/lendery/maintenance/{repair_case['id']}/events",
            json={
                "event_type": "repair_completed",
                "note": "Item is ready for circulation.",
            },
        )
        self.assertEqual(completed.status_code, 201, completed.text)
        self.assertEqual(completed.json()["status"], "resolved")
        self.assertIsNotNone(completed.json()["resolved_at"])

        history = self.manager.get(
            f"/lendery/items/{item['id']}/maintenance"
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()), 1)
        self.assertEqual(len(history.json()[0]["events"]), 3)
        self.assertEqual(
            history.json()[0]["events"][0]["created_by_name"],
            "manager",
        )

    def test_maintenance_queue_lists_open_cases_across_items_and_is_editor_only(
        self,
    ) -> None:
        first_item = self.create_item()
        second = self.manager.post(
            "/lendery/items",
            json={"name": "Sewing machine", "barcode": "KIT-2"},
        )
        self.assertEqual(second.status_code, 201, second.text)
        second_item = second.json()

        open_case = self.manager.post(
            f"/lendery/items/{first_item['id']}/maintenance",
            json={"title": "Missing remote"},
        )
        self.assertEqual(open_case.status_code, 201, open_case.text)

        resolved_case = self.manager.post(
            f"/lendery/items/{second_item['id']}/maintenance",
            json={"title": "Needle replaced", "status": "resolved"},
        )
        self.assertEqual(resolved_case.status_code, 201, resolved_case.text)

        self.assertEqual(
            self.viewer.get("/lendery/maintenance").status_code, 403
        )

        queue = self.manager.get("/lendery/maintenance")
        self.assertEqual(queue.status_code, 200, queue.text)
        entries = queue.json()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Missing remote")
        self.assertEqual(entries[0]["item_id"], first_item["id"])
        self.assertEqual(entries[0]["item_name"], "Projector kit")
        self.assertEqual(entries[0]["item_barcode"], "KIT-1")

    def test_suggestions_are_idempotent_and_managed_by_lendery_editors(
        self,
    ) -> None:
        payload = {
            "item_name": "Portable induction cooktop",
            "description": "Useful for cooking demonstrations and programs.",
            "category": "Kitchen",
            "product_url": "https://example.com/cooktop",
            "additional_notes": "A carrying case would be helpful.",
            "submission_key": "suggestion-test-key",
        }
        self.assertEqual(
            self.anonymous.post("/lendery/suggestions", json=payload).status_code,
            401,
        )

        created = self.viewer.post("/lendery/suggestions", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        duplicate = self.viewer.post("/lendery/suggestions", json=payload)
        self.assertEqual(duplicate.status_code, 201, duplicate.text)
        self.assertEqual(duplicate.json()["id"], created.json()["id"])
        self.assertIsNotNone(created.json()["submitted_at"])
        self.assertEqual(created.json()["submitted_by_name"], "Viewer")

        invalid = self.viewer.post(
            "/lendery/suggestions",
            json={**payload, "submission_key": "another-key", "description": "  "},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(self.viewer.get("/lendery/suggestions").status_code, 403)

        suggestions = self.manager.get("/lendery/suggestions")
        self.assertEqual(suggestions.status_code, 200, suggestions.text)
        self.assertEqual(len(suggestions.json()), 1)
        suggestion_id = suggestions.json()[0]["id"]
        self.assertEqual(
            self.manager.get(f"/lendery/suggestions/{suggestion_id}").status_code,
            200,
        )
        self.assertEqual(
            self.viewer.delete(f"/lendery/suggestions/{suggestion_id}").status_code,
            403,
        )
        self.assertEqual(
            self.manager.delete(f"/lendery/suggestions/{suggestion_id}").status_code,
            204,
        )
        self.assertEqual(
            self.manager.get(f"/lendery/suggestions/{suggestion_id}").status_code,
            404,
        )

    def test_users_can_save_up_to_four_permission_aware_quick_actions(
        self,
    ) -> None:
        me = self.viewer.get("/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(
            me.json()["quick_actions"],
            [
                "lendery-suggest-item",
                "bookclub-add-member",
                "bookclub-add-book",
            ],
        )

        denied = self.viewer.put(
            "/auth/quick-actions",
            json={"actions": ["lendery-add-item"]},
        )
        self.assertEqual(denied.status_code, 403, denied.text)

        selected = ["bookclub-add-book", "lendery-suggest-item"]
        updated = self.viewer.put(
            "/auth/quick-actions",
            json={"actions": selected},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["quick_actions"], selected)
        self.assertEqual(
            self.viewer.get("/auth/me").json()["quick_actions"], selected
        )

        too_many = self.manager.put(
            "/auth/quick-actions",
            json={
                "actions": [
                    "lendery-suggest-item",
                    "lendery-add-item",
                    "lendery-report-issue",
                    "bookclub-add-member",
                    "bookclub-add-book",
                ]
            },
        )
        self.assertEqual(too_many.status_code, 422)

    def test_shared_lendery_login_endpoints_are_removed(self) -> None:
        self.assertEqual(
            self.anonymous.post(
                "/lendery/auth/login",
                json={"username": "clerk", "password": "old-password"},
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
