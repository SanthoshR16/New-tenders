import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

import app as tender_app
import decision_relay


class EvolutionWhatsAppTests(unittest.TestCase):
    ENV = {
        "EVO_BASE_URL": "https://evolution.example",
        "EVO_API_KEY": "test-evolution-key",
        "EVO_INSTANCE": "tenderrelay",
        "WHATSAPP_GROUP_JID": "120363428714377742@g.us",
    }

    def test_send_whatsapp_text_checks_instance_and_sends_group_message(self):
        state_response = unittest.mock.Mock()
        state_response.json.return_value = {"instance": {"state": "open"}}
        state_response.raise_for_status.return_value = None
        send_response = unittest.mock.Mock()
        send_response.raise_for_status.return_value = None
        with patch.dict(os.environ, self.ENV), \
                patch.object(decision_relay.requests, "get", return_value=state_response) as get, \
                patch.object(decision_relay.requests, "post", return_value=send_response) as post:
            sent = decision_relay.send_whatsapp_text("Example - BID")

        self.assertTrue(sent)
        get.assert_called_once_with(
            "https://evolution.example/instance/connectionState/tenderrelay",
            headers={"apikey": "test-evolution-key"},
            timeout=15,
        )
        post.assert_called_once_with(
            "https://evolution.example/message/sendText/tenderrelay",
            headers={
                "apikey": "test-evolution-key",
                "Content-Type": "application/json",
            },
            json={
                "number": "120363428714377742@g.us",
                "text": "Example - BID",
            },
            timeout=15,
        )

    def test_send_whatsapp_text_retries_three_times_and_returns_false(self):
        failure = requests.HTTPError("temporary failure")
        failed_response = unittest.mock.Mock()
        failed_response.raise_for_status.side_effect = failure
        with patch.dict(os.environ, self.ENV), \
                patch.object(decision_relay.requests, "get") as get, \
                patch.object(
                    decision_relay.requests,
                    "post",
                    return_value=failed_response,
                ) as post, \
                patch.object(decision_relay.time, "sleep") as sleep:
            get.return_value.json.return_value = {"instance": {"state": "open"}}
            self.assertFalse(decision_relay.send_whatsapp_text("Example - NO BID"))

        self.assertEqual(post.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2, 4])

    def test_send_whatsapp_text_warns_but_attempts_when_instance_is_not_open(self):
        state_response = unittest.mock.Mock()
        state_response.json.return_value = {"instance": {"state": "close"}}
        state_response.raise_for_status.return_value = None
        send_response = unittest.mock.Mock()
        send_response.raise_for_status.return_value = None
        with patch.dict(os.environ, self.ENV), \
                patch.object(decision_relay.requests, "get", return_value=state_response), \
                patch.object(
                    decision_relay.requests,
                    "post",
                    return_value=send_response,
                ) as post, \
                self.assertLogs(decision_relay.logger, level="WARNING") as logs:
            self.assertTrue(decision_relay.send_whatsapp_text("scan summary"))

        self.assertIn("not open", logs.output[0])
        post.assert_called_once()


class DecisionStorageTests(unittest.TestCase):
    def test_store_decision_uses_required_schema_and_fields(self):
        connection = unittest.mock.MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"id": 31}
        with patch.object(decision_relay, "_connect_postgres", return_value=connection):
            decision_id = decision_relay.store_decision(
                tender_id="IND2712",
                tender_title="Example tender",
                decision="BID",
                decided_by="Kamal Sir",
                message_text="📌 Tender: IND2712 - Example tender",
            )

        self.assertEqual(decision_id, 31)
        query, values = cursor.execute.call_args.args
        self.assertIn("INSERT INTO tender_app.tender_decisions", query)
        self.assertEqual(values, (
            "IND2712",
            "Example tender",
            "BID",
            "Kamal Sir",
            "📌 Tender: IND2712 - Example tender",
        ))
        connection.commit.assert_called_once()

    def test_relay_marks_sent_only_after_whatsapp_accepts(self):
        connection = unittest.mock.MagicMock()
        cursor = unittest.mock.MagicMock()
        cursor.__enter__.return_value = cursor
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = [{
            "id": 5,
            "tender_id": "IND2712",
            "tender_title": "Example tender",
            "decision": "NO BID",
            "decided_by": "Kamal Sir",
            "message_text": "🚫 Tender IND2712 - Example tender",
        }]
        with patch.object(decision_relay, "_connect_postgres", return_value=connection), \
                patch.object(decision_relay, "send_whatsapp_text", return_value=False) as send:
            result = decision_relay.relay_pending_decisions()

        self.assertEqual(result, {"sent": 0, "failed": 1})
        send.assert_called_once_with("🚫 Tender IND2712 - Example tender")
        updates = [
            call.args[0]
            for call in cursor.execute.call_args_list
            if "UPDATE tender_app.tender_decisions" in call.args[0]
        ]
        self.assertEqual(updates, [])

    def test_relay_sets_sent_after_successful_whatsapp_send(self):
        connection = unittest.mock.MagicMock()
        cursor = unittest.mock.MagicMock()
        cursor.__enter__.return_value = cursor
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = [{
            "id": 6,
            "tender_id": "IND2713",
            "tender_title": "Example tender",
            "decision": "BID",
            "decided_by": "Developer",
            "message_text": "✅ Tender IND2713 - Example tender",
        }]
        events = []
        cursor.execute.side_effect = lambda query, *_args: events.append(
            "update" if "UPDATE tender_app.tender_decisions" in query else "sql"
        )
        def send(_message):
            events.append("send")
            return True

        with patch.object(decision_relay, "_connect_postgres", return_value=connection), \
                patch.object(
                    decision_relay,
                    "send_whatsapp_text",
                    side_effect=send,
                ) as send_mock:
            result = decision_relay.relay_pending_decisions()

        self.assertEqual(result, {"sent": 1, "failed": 0})
        self.assertLess(events.index("send"), events.index("update"))
        send_mock.assert_called_once_with("✅ Tender IND2713 - Example tender")
        self.assertEqual(connection.commit.call_count, 2)

    def test_cleanup_deletes_only_successfully_sent_decisions(self):
        connection = unittest.mock.MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{"id": 7}]
        with patch.object(decision_relay, "_connect_postgres", return_value=connection):
            cleared = decision_relay.clear_sent_decisions()

        self.assertEqual(cleared, 1)
        query = cursor.execute.call_args.args[0]
        self.assertIn("DELETE FROM tender_app.tender_decisions", query)
        self.assertIn("WHERE sent = TRUE", query)
        self.assertNotIn("DELETE FROM tender_app.tender_decisions;", query)

    def test_redis_cleanup_scans_only_tender_prefixed_keys(self):
        client = unittest.mock.MagicMock()
        client.scan_iter.return_value = iter(["tender:one", "tender:two"])
        client.delete.return_value = 2
        redis_mock = SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *_args, **_kwargs: client))
        with patch.dict(os.environ, {"REDIS_URL": "redis://test"}), \
                patch.dict(sys.modules, {"redis": redis_mock}):
            cleared = decision_relay.clear_tender_redis_keys()

        self.assertEqual(cleared, 2)
        client.scan_iter.assert_called_once_with(match="tender:*", count=500)
        client.delete.assert_called_once_with("tender:one", "tender:two")


class DecisionRelayRouteTests(unittest.TestCase):
    TOKEN = "test-relay-token-only"

    def setUp(self):
        self.client = tender_app.app.test_client()

    def headers(self):
        return {"Authorization": f"Bearer {self.TOKEN}"}

    def test_manual_relay_requires_auth_and_returns_counts(self):
        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.TOKEN}), \
                patch.object(
                    tender_app.decision_relay,
                    "relay_pending_decisions",
                    return_value={"sent": 2, "failed": 1},
                ) as relay:
            denied = self.client.post("/relay-decisions")
            accepted = self.client.post("/relay-decisions", headers=self.headers())

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(
            accepted.get_json(),
            {"status": "ok", "sent": 2, "failed": 1},
        )
        relay.assert_called_once()

    def test_test_whatsapp_route_requires_bearer_and_reports_send_result(self):
        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.TOKEN}), \
                patch.object(
                    tender_app.decision_relay,
                    "send_whatsapp_text",
                    return_value=True,
                ) as send:
            denied = self.client.post("/test-whatsapp")
            accepted = self.client.post("/test-whatsapp", headers=self.headers())

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json(), {"status": "ok", "sent": True})
        send.assert_called_once_with("Test message from tenderrelay")

    def test_test_whatsapp_route_returns_failure_without_failing_open(self):
        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.TOKEN}), \
                patch.object(
                    tender_app.decision_relay,
                    "send_whatsapp_text",
                    return_value=False,
                ) as send:
            response = self.client.post("/test-whatsapp", headers=self.headers())

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json(), {"status": "error", "sent": False})
        send.assert_called_once_with("Test message from tenderrelay")

    def test_scan_start_relays_then_clears_owned_storage_only(self):
        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.TOKEN}), \
                patch.object(
                    tender_app.decision_relay,
                    "relay_pending_decisions",
                    return_value={"sent": 1, "failed": 1},
                ) as relay, \
                patch.object(
                    tender_app.decision_relay,
                    "clear_sent_decisions",
                    return_value=1,
                ) as clear_rows, \
                patch.object(
                    tender_app.decision_relay,
                    "clear_tender_redis_keys",
                    return_value=3,
                ) as clear_keys, \
                patch.object(
                    tender_app.decision_relay,
                    "count_unsent_decisions",
                    return_value=1,
                ):
            response = self.client.post(
                "/api/relay/scan-start",
                headers=self.headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "status": "ok",
            "relay": {"sent": 1, "failed": 1},
            "rows_cleared": 1,
            "redis_keys_cleared": 3,
            "unsent_retained": 1,
        })
        relay.assert_called_once()
        clear_rows.assert_called_once()
        clear_keys.assert_called_once()

    def test_scan_summary_sends_short_count_and_rejects_invalid_count(self):
        with patch.dict(os.environ, {"RELAY_API_TOKEN": self.TOKEN}), \
                patch.object(
                    tender_app.decision_relay,
                    "send_whatsapp_text",
                    return_value=True,
                ) as send:
            response = self.client.post(
                "/api/relay/scan-summary",
                json={"new_tenders": 4},
                headers=self.headers(),
            )
            invalid = self.client.post(
                "/api/relay/scan-summary",
                json={"new_tenders": True},
                headers=self.headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "sent": True})
        send.assert_called_once_with("Tender scan complete. New tenders found: 4.")
        self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main()
