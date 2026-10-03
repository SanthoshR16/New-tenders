import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

import app as tender_app


class WhatsAppDecisionSharingTests(unittest.TestCase):
    RELAY_TOKEN = "test-relay-token-that-is-not-a-production-secret"

    @classmethod
    def setUpClass(cls):
        cls.original_db_path = tender_app.DB_PATH
        cls.original_secret_key = tender_app.app.secret_key
        cls.original_codes = {
            env_name: os.environ.get(env_name)
            for env_name in tender_app.AUTH_CODE_ENV.values()
        }
        cls.codes = {
            "Developer": "test-developer-access-code-" + ("x" * 24),
            "Kamal Sir": "test-kamal-access-code-" + ("y" * 24),
            "Uday Sir": "test-uday-access-code-" + ("z" * 24),
        }
        for role, env_name in tender_app.AUTH_CODE_ENV.items():
            os.environ[env_name] = cls.codes[role]
        tender_app._configure_session_secret()

        cls.temp_dir = tempfile.TemporaryDirectory()
        tender_app.DB_PATH = os.path.join(cls.temp_dir.name, "whatsapp_test.db")
        tender_app.init_db()
        tender_app.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        tender_app.DB_PATH = cls.original_db_path
        tender_app.app.secret_key = cls.original_secret_key
        for env_name, value in cls.original_codes.items():
            if value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = value
        cls.temp_dir.cleanup()

    def setUp(self):
        with closing(tender_app.get_db()) as conn:
            conn.execute("DELETE FROM pending_sync")
            conn.commit()
        self.relay_patches = [
            patch.object(tender_app.decision_relay, "store_decision", return_value=1),
            patch.object(tender_app.decision_relay, "relay_pending_decisions", return_value={"sent": 1, "failed": 0}),
            patch.object(tender_app.decision_relay, "get_decision_sent", return_value=True),
        ]
        self.relay_mocks = [relay_patch.start() for relay_patch in self.relay_patches]
        self.client = tender_app.app.test_client()
        login = self.client.post(
            "/api/auth/login",
            json={"access_code": self.codes["Developer"]},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self):
        for relay_patch in self.relay_patches:
            relay_patch.stop()

    def _submit_approval(self):
        response = self.client.post(
            "/api/submit_allocation",
            json={
                "tender_no": "IND2712",
                "tender_name": "Tender IND2712",
                "allocations": [{
                    "item_id": "1",
                    "item_name": "Equipment Scope",
                    "quantity": "1",
                    "manufacturer": "GMPL",
                }],
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def _pending_row(self, action_id):
        with closing(tender_app.get_db()) as conn:
            row = conn.execute(
                "SELECT action_type, data_json, synced FROM pending_sync WHERE id = ?",
                (action_id,),
            ).fetchone()
        return row

    def _relay_headers(self, token=None):
        token = self.RELAY_TOKEN if token is None else token
        return {"Authorization": f"Bearer {token}"}

    def test_relay_pending_includes_synced_undelivered_decisions(self):
        with closing(tender_app.get_db()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO pending_sync (action_type, tender_no, data_json, synced)
                VALUES ('BID_ALLOCATION', ?, ?, 1)
                """,
                ("IND2712", json.dumps({
                    "tender_no": "IND2712",
                    "tender_name": "Tender IND2712",
                    "approved_by": "Developer",
                    "allocations": [{
                        "item_id": "1",
                        "item_name": "Equipment Scope",
                        "quantity": "1",
                        "manufacturer": "GMPL",
                    }],
                    "requires_whatsapp_share": True,
                    "whatsapp_shared": False,
                })),
            )
            action_id = cursor.lastrowid
            conn.commit()
        self.assertEqual(self._pending_row(action_id)["synced"], 1)

        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.RELAY_TOKEN}):
            response = self.client.get(
                "/api/relay/pending",
                headers=self._relay_headers(),
            )
        self.assertEqual(response.status_code, 200)
        actions = response.get_json()
        self.assertEqual([action["id"] for action in actions], [action_id])
        self.assertEqual(actions[0]["action_type"], "BID_ALLOCATION")
        self.assertEqual(actions[0]["tender_no"], "IND2712")
        self.assertEqual(actions[0]["approved_by"], "Developer")
        self.assertIn("created_at", actions[0])
        self.assertEqual(actions[0]["data"]["allocations"][0]["manufacturer"], "GMPL")

    def test_relay_pending_excludes_delivered_and_non_decision_actions(self):
        result = self._submit_approval()
        action_id = result["action_id"]
        with closing(tender_app.get_db()) as conn:
            conn.execute(
                "UPDATE pending_sync SET relay_delivered = 1 WHERE id = ?",
                (action_id,),
            )
            conn.execute(
                "INSERT INTO pending_sync (action_type, tender_no, data_json, synced) VALUES (?, ?, ?, 0)",
                ("OTHER_ACTION", "IND-NOT-DECISION", "{}"),
            )
            conn.commit()

        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.RELAY_TOKEN}):
            response = self.client.get(
                "/api/relay/pending",
                headers=self._relay_headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_relay_endpoints_reject_invalid_bearer_token(self):
        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.RELAY_TOKEN}):
            pending = self.client.get(
                "/api/relay/pending",
                headers=self._relay_headers("wrong-relay-token"),
            )
            mark = self.client.post(
                "/api/relay/mark-delivered",
                json={"id": 1},
                headers=self._relay_headers("wrong-relay-token"),
            )
        self.assertEqual(pending.status_code, 401)
        self.assertEqual(mark.status_code, 401)

    def test_relay_token_missing_fails_closed(self):
        result = self._submit_approval()
        with patch.dict(os.environ, {"RELAY_API_TOKEN": ""}):
            pending = self.client.get("/api/relay/pending")
            mark = self.client.post(
                "/api/relay/mark-delivered",
                json={"id": result["action_id"]},
            )
        self.assertEqual(pending.status_code, 503)
        self.assertEqual(mark.status_code, 503)
        self.assertNotIn("RELAY_API_TOKEN", pending.get_data(as_text=True))

    def test_mark_relay_delivered_is_idempotent_and_preserves_record(self):
        result = self._submit_approval()
        action_id = result["action_id"]
        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.RELAY_TOKEN}):
            first = self.client.post(
                "/api/relay/mark-delivered",
                json={"id": action_id},
                headers=self._relay_headers(),
            )
            second = self.client.post(
                "/api/relay/mark-delivered",
                json={"id": action_id},
                headers=self._relay_headers(),
            )
            pending = self.client.get(
                "/api/relay/pending",
                headers=self._relay_headers(),
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.get_json(), {
            "status": "ok",
            "id": action_id,
            "relay_delivered": True,
        })
        self.assertEqual(second.get_json(), first.get_json())
        self.assertEqual(pending.get_json(), [])
        self.assertIsNotNone(self._pending_row(action_id))

    def test_relay_mark_delivered_validates_ids_and_only_marks_decisions(self):
        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.RELAY_TOKEN}):
            invalid = self.client.post(
                "/api/relay/mark-delivered",
                json={"id": True},
                headers=self._relay_headers(),
            )
            missing = self.client.post(
                "/api/relay/mark-delivered",
                json={"id": 999999},
                headers=self._relay_headers(),
            )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(missing.status_code, 404)

    def test_existing_pending_sync_table_migrates_undelivered_by_default(self):
        original_db_path = tender_app.DB_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_db_path = os.path.join(temp_dir, "legacy.db")
            with closing(sqlite3.connect(legacy_db_path)) as conn:
                conn.execute("""
                    CREATE TABLE pending_sync (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        action_type TEXT,
                        tender_no TEXT,
                        data_json TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        synced INTEGER DEFAULT 0
                    )
                """)
                conn.execute(
                    "INSERT INTO pending_sync (action_type, tender_no, data_json, synced) VALUES (?, ?, ?, 1)",
                    ("NOT_BID", "IND-LEGACY", json.dumps({
                        "tender_no": "IND-LEGACY",
                        "approved_by": "Kamal Sir",
                    })),
                )
                conn.commit()

            try:
                tender_app.DB_PATH = legacy_db_path
                tender_app.init_db()
                with closing(tender_app.get_db()) as conn:
                    row = conn.execute(
                        "SELECT synced, relay_delivered FROM pending_sync WHERE tender_no = ?",
                        ("IND-LEGACY",),
                    ).fetchone()
                self.assertEqual((row["synced"], row["relay_delivered"]), (1, 0))
            finally:
                tender_app.DB_PATH = original_db_path

    def test_approval_returns_prefilled_whatsapp_confirmation(self):
        result = self._submit_approval()
        self.assertEqual(result["status"], "ok")
        self.assertIn("✅ *BID APPROVED & MANUFACTURER ALLOCATED*", result["whatsapp_text"])
        self.assertIn("IND2712 - Tender IND2712", result["whatsapp_text"])
        self.assertIn("*Equipment Scope* (Qty: 1) ➔ *GMPL*", result["whatsapp_text"])
        row = self._pending_row(result["action_id"])
        payload = json.loads(row["data_json"])
        self.assertFalse(payload["requires_whatsapp_share"])
        self.assertFalse(payload["whatsapp_shared"])
        self.assertEqual(row["synced"], 0)
        self.assertTrue(result["whatsapp_sent"])
        self.relay_mocks[0].assert_called_once_with(
            tender_id="IND2712",
            tender_title="Tender IND2712",
            decision="BID",
            decided_by="Developer",
        )
        self.relay_mocks[1].assert_called_once()

        page = self.client.get("/bid?tender=IND2712")
        self.assertNotIn(b"api.whatsapp.com/send", page.data)
        self.assertNotIn(b"Open WhatsApp", page.data)
        self.assertIn(b"WhatsApp delivery is queued for automatic retry.", page.data)

    def test_rejection_returns_prefilled_whatsapp_confirmation(self):
        response = self.client.post(
            "/api/record_dontbid",
            json={"tender_no": "IND2495/CALL-3"},
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertIn("🚫 *TENDER DECISION — NOT BID*", result["whatsapp_text"])
        self.assertIn("IND2495/CALL-3", result["whatsapp_text"])
        self.assertIn("Developer", result["whatsapp_text"])
        self.assertTrue(result["whatsapp_sent"])
        self.relay_mocks[0].assert_called_once_with(
            tender_id="IND2495/CALL-3",
            tender_title="IND2495/CALL-3",
            decision="NO BID",
            decided_by="Developer",
        )
        page = self.client.get("/dontbid?tender=IND2495/CALL-3")
        self.assertNotIn(b"api.whatsapp.com/send", page.data)
        self.assertNotIn(b"Open WhatsApp", page.data)
        self.assertIn(b"DECISION RECORDED", page.data)
        self.assertNotIn(b"window.location.replace('/decision-sending/' + actionId)", page.data)

    def test_sending_page_prepares_manual_whatsapp_and_closes_after_confirmation(self):
        result = self._submit_approval()
        page = self.client.get(f"/decision-sending/{result['action_id']}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Continue to WhatsApp", page.data)
        self.assertIn(b"Choose the correct decision group", page.data)
        self.assertIn(b"Sent to the group", page.data)
        self.assertIn(b"window.close()", page.data)
        self.assertIn(b"api.whatsapp.com/send?text=", page.data)

    def test_sending_page_requires_member_login(self):
        result = self._submit_approval()
        response = tender_app.app.test_client().get(
            f"/decision-sending/{result['action_id']}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Member access code", response.data)

    def test_automated_decision_needs_only_local_sync_and_legacy_share_still_works(self):
        result = self._submit_approval()
        action_id = result["action_id"]

        synced = tender_app.app.test_client().post(
            "/api/mark_synced",
            json={"id": action_id},
        )
        self.assertEqual(synced.status_code, 200)
        self.assertIsNone(self._pending_row(action_id))

        with closing(tender_app.get_db()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO pending_sync (action_type, tender_no, data_json, synced)
                VALUES ('NOT_BID', ?, ?, 0)
                """,
                ("IND-LEGACY-SHARE", json.dumps({
                    "tender_no": "IND-LEGACY-SHARE",
                    "approved_by": "Developer",
                    "requires_whatsapp_share": True,
                    "whatsapp_shared": False,
                })),
            )
            legacy_id = cursor.lastrowid
            conn.commit()

        synced_first = tender_app.app.test_client().post(
            "/api/mark_synced",
            json={"id": legacy_id},
        )
        self.assertIn("waiting for WhatsApp send", synced_first.get_json()["message"])
        self.assertEqual(self._pending_row(legacy_id)["synced"], 1)

        shared_last = self.client.post(
            "/api/mark_whatsapp_shared",
            json={"id": legacy_id},
        )
        self.assertEqual(shared_last.status_code, 200)
        self.assertIsNone(self._pending_row(legacy_id))

    def test_share_confirmation_requires_member_session(self):
        result = self._submit_approval()
        response = tender_app.app.test_client().post(
            "/api/mark_whatsapp_shared",
            json={"id": result["action_id"]},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIsNotNone(self._pending_row(result["action_id"]))

    def test_scanner_acknowledgement_validates_id_and_removes_legacy_actions(self):
        bad_request = tender_app.app.test_client().post(
            "/api/mark_synced",
            json={"id": "not-an-id"},
        )
        self.assertEqual(bad_request.status_code, 400)

        with closing(tender_app.get_db()) as conn:
            cursor = conn.execute(
                "INSERT INTO pending_sync (action_type, tender_no, data_json, synced) VALUES (?, ?, ?, 0)",
                ("NOT_BID", "IND-LEGACY", json.dumps({"tender_no": "IND-LEGACY"})),
            )
            legacy_id = cursor.lastrowid
            conn.commit()
        response = tender_app.app.test_client().post(
            "/api/mark_synced",
            json={"id": legacy_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._pending_row(legacy_id))


if __name__ == "__main__":
    unittest.main()
