import json
import os
import tempfile
import unittest
from contextlib import closing

import app as tender_app


class WhatsAppDecisionSharingTests(unittest.TestCase):
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
        self.client = tender_app.app.test_client()
        login = self.client.post(
            "/api/auth/login",
            json={"access_code": self.codes["Developer"]},
        )
        self.assertEqual(login.status_code, 200)

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

    def test_approval_returns_prefilled_whatsapp_confirmation(self):
        result = self._submit_approval()
        self.assertEqual(result["status"], "ok")
        self.assertIn("✅ *BID APPROVED & MANUFACTURER ALLOCATED*", result["whatsapp_text"])
        self.assertIn("IND2712 - Tender IND2712", result["whatsapp_text"])
        self.assertIn("*Equipment Scope* (Qty: 1) ➔ *GMPL*", result["whatsapp_text"])
        row = self._pending_row(result["action_id"])
        payload = json.loads(row["data_json"])
        self.assertTrue(payload["requires_whatsapp_share"])
        self.assertFalse(payload["whatsapp_shared"])
        self.assertEqual(row["synced"], 0)

        page = self.client.get("/bid?tender=IND2712")
        self.assertNotIn(b"api.whatsapp.com/send", page.data)
        self.assertNotIn(b"Open WhatsApp", page.data)
        self.assertIn(b"const sendingWindow = window.open('about:blank', '_blank')", page.data)
        self.assertIn(b"sendingWindow.location.href = sendingUrl", page.data)
        self.assertIn(b"window.location.assign(sendingUrl)", page.data)

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
        page = self.client.get("/dontbid?tender=IND2495/CALL-3")
        self.assertNotIn(b"api.whatsapp.com/send", page.data)
        self.assertNotIn(b"Open WhatsApp", page.data)
        self.assertIn(b"const sendingWindow = window.open('about:blank', '_blank')", page.data)
        self.assertIn(b"sendingWindow.location.href = sendingUrl", page.data)
        self.assertIn(b"window.location.replace(sendingUrl)", page.data)
        self.assertIn(b"window.location.replace('/decision-sending/' + actionId)", page.data)

    def test_sending_page_prepares_manual_whatsapp_and_closes_after_confirmation(self):
        result = self._submit_approval()
        page = self.client.get(f"/decision-sending/{result['action_id']}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Continue to WhatsApp", page.data)
        self.assertIn(b"Copy Message", page.data)
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

    def test_action_is_deleted_after_share_and_local_sync_in_either_order(self):
        result = self._submit_approval()
        action_id = result["action_id"]

        shared = self.client.post(
            "/api/mark_whatsapp_shared",
            json={"id": action_id},
        )
        self.assertEqual(shared.status_code, 200)
        self.assertIn("after the local scanner syncs", shared.get_json()["message"])
        self.assertIsNotNone(self._pending_row(action_id))

        synced = tender_app.app.test_client().post(
            "/api/mark_synced",
            json={"id": action_id},
        )
        self.assertEqual(synced.status_code, 200)
        self.assertIsNone(self._pending_row(action_id))

        second = self._submit_approval()
        second_id = second["action_id"]
        synced_first = tender_app.app.test_client().post(
            "/api/mark_synced",
            json={"id": second_id},
        )
        self.assertIn("waiting for WhatsApp send", synced_first.get_json()["message"])
        self.assertEqual(self._pending_row(second_id)["synced"], 1)

        shared_last = self.client.post(
            "/api/mark_whatsapp_shared",
            json={"id": second_id},
        )
        self.assertEqual(shared_last.status_code, 200)
        self.assertIsNone(self._pending_row(second_id))

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
