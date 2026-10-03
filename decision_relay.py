import logging
import os
import time

import requests


logger = logging.getLogger("tender_decision_relay")
_RELAY_LOCK_NAME = "tender:decision-relay"
_SEND_TIMEOUT_SECONDS = 15
_SEND_ATTEMPTS = 4


def _connect_postgres():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    import psycopg2
    from psycopg2.extras import RealDictCursor

    connection = psycopg2.connect(
        database_url,
        connect_timeout=10,
        cursor_factory=RealDictCursor,
    )
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS tender_app")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tender_app.tender_decisions (
                id BIGSERIAL PRIMARY KEY,
                tender_id TEXT NOT NULL,
                tender_title TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('BID', 'NO BID')),
                decided_by TEXT NOT NULL,
                decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sent BOOLEAN NOT NULL DEFAULT FALSE,
                sent_at TIMESTAMPTZ,
                message_text TEXT
            )
        """)
        cursor.execute("""
            ALTER TABLE tender_app.tender_decisions
            ADD COLUMN IF NOT EXISTS message_text TEXT
        """)
    connection.commit()
    return connection


def store_decision(tender_id, tender_title, decision, decided_by, message_text):
    if decision not in {"BID", "NO BID"}:
        raise ValueError("Decision must be BID or NO BID.")
    if not tender_id or not tender_title or not decided_by or not message_text:
        raise ValueError("Tender ID, title, approver, and message are required.")

    connection = _connect_postgres()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO tender_app.tender_decisions
                    (tender_id, tender_title, decision, decided_by, message_text)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (tender_id, tender_title, decision, decided_by, message_text))
            decision_id = cursor.fetchone()["id"]
        connection.commit()
        return decision_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_unsent_decision(decision_id):
    connection = _connect_postgres()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM tender_app.tender_decisions
                WHERE id = %s AND sent = FALSE
            """, (decision_id,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_decision_sent(decision_id):
    connection = _connect_postgres()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sent FROM tender_app.tender_decisions WHERE id = %s
            """, (decision_id,))
            row = cursor.fetchone()
        return bool(row["sent"]) if row else False
    finally:
        connection.close()


def send_whatsapp_text(text):
    return send_whatsapp_text_result(text)["sent"]


def send_whatsapp_text_result(text):
    base_url = os.environ.get("EVO_BASE_URL", "").strip().rstrip("/")
    api_key = os.environ.get("EVO_API_KEY", "").strip()
    instance = os.environ.get("EVO_INSTANCE", "").strip()
    group_jid = os.environ.get("WHATSAPP_GROUP_JID", "").strip()
    missing = [
        name for name, value in (
            ("EVO_BASE_URL", base_url),
            ("EVO_API_KEY", api_key),
            ("EVO_INSTANCE", instance),
            ("WHATSAPP_GROUP_JID", group_jid),
        )
        if not value
    ]
    if missing:
        logger.error(
            "WhatsApp send configuration is incomplete; missing: %s.",
            ", ".join(missing),
        )
        return {"sent": False, "error": "missing_configuration", "missing": missing}

    headers = {"apikey": api_key, "Content-Type": "application/json"}
    state_url = f"{base_url}/instance/connectionState/{instance}"
    instance_state = "unknown"
    try:
        state_response = requests.get(
            state_url,
            headers={"apikey": api_key},
            timeout=_SEND_TIMEOUT_SECONDS,
        )
        state_response.raise_for_status()
        state_data = state_response.json()
        instance_state = (
            (state_data.get("instance") or {}).get("state")
            or state_data.get("state")
            or "unknown"
        )
        if instance_state != "open":
            logger.warning(
                "Evolution API instance %r is not open (state=%r); attempting message send anyway.",
                instance,
                instance_state,
            )
    except (requests.RequestException, ValueError, AttributeError) as error:
        state_error = type(error).__name__
        logger.warning(
            "Could not verify Evolution API instance %r connection state; attempting message send anyway.",
            instance,
            exc_info=True,
        )
    else:
        state_error = None

    send_url = f"{base_url}/message/sendText/{instance}"
    last_error = None
    for attempt in range(_SEND_ATTEMPTS):
        if attempt:
            time.sleep(2 ** (attempt - 1))
        try:
            response = requests.post(
                send_url,
                headers=headers,
                json={"number": group_jid, "text": text},
                timeout=_SEND_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            logger.info("WhatsApp message accepted by Evolution API for instance %r.", instance)
            return {
                "sent": True,
                "instance_state": instance_state,
            }
        except requests.RequestException as error:
            response = getattr(error, "response", None)
            last_error = (
                f"http_{response.status_code}"
                if response is not None
                else type(error).__name__
            )
            logger.exception(
                "WhatsApp send attempt %d/%d failed for instance %r (%s).",
                attempt + 1,
                _SEND_ATTEMPTS,
                instance,
                last_error,
            )

    logger.error(
        "WhatsApp message was not accepted after %d attempts; it remains queued for retry (%s).",
        _SEND_ATTEMPTS,
        last_error or "unknown_error",
    )
    return {
        "sent": False,
        "error": last_error or "unknown_error",
        "instance_state": instance_state,
        "connection_check_error": state_error,
    }


def relay_pending_decisions():
    connection = _connect_postgres()
    sent_count = 0
    failed_count = 0
    lock_acquired = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_lock(hashtext(%s)::bigint)",
                (_RELAY_LOCK_NAME,),
            )
            lock_acquired = True
            cursor.execute("""
                SELECT id, tender_id, tender_title, decision, decided_by, message_text
                FROM tender_app.tender_decisions
                WHERE sent = FALSE
                ORDER BY id
            """)
            decisions = cursor.fetchall()

        for decision in decisions:
            message = decision.get("message_text") or _format_stored_decision(decision)
            if not send_whatsapp_text(message):
                failed_count += 1
                continue

            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        UPDATE tender_app.tender_decisions
                        SET sent = TRUE, sent_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND sent = FALSE
                    """, (decision["id"],))
                connection.commit()
                sent_count += 1
            except Exception:
                connection.rollback()
                logger.exception(
                    "WhatsApp accepted decision ID %s, but its sent status could not be saved.",
                    decision["id"],
                )
                failed_count += 1

        logger.info(
            "Decision relay finished: sent=%d, unsent_failures=%d.",
            sent_count,
            failed_count,
        )
        return {"sent": sent_count, "failed": failed_count}
    except Exception:
        connection.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtext(%s)::bigint)",
                        (_RELAY_LOCK_NAME,),
                    )
                connection.commit()
            except Exception:
                logger.exception("Could not explicitly release the decision relay lock.")
        connection.close()


def _format_stored_decision(decision):
    heading = (
        "✅ *BID APPROVED & MANUFACTURER ALLOCATED*"
        if decision["decision"] == "BID"
        else "🚫 *TENDER DECISION — NOT BID*"
    )
    return "\n".join((
        heading,
        "",
        f"📌 *Tender:* {decision['tender_id']} - {decision['tender_title']}",
        f"👤 *Decision By:* {decision['decided_by']}",
    ))


def clear_sent_decisions():
    connection = _connect_postgres()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM tender_app.tender_decisions
                WHERE sent = TRUE
                RETURNING id
            """)
            cleared_count = len(cursor.fetchall())
        connection.commit()
        logger.info("Cleared %d successfully sent tender decision row(s).", cleared_count)
        return cleared_count
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def count_unsent_decisions():
    connection = _connect_postgres()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS count
                FROM tender_app.tender_decisions
                WHERE sent = FALSE
            """)
            return cursor.fetchone()["count"]
    finally:
        connection.close()


def clear_tender_redis_keys():
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError("REDIS_URL is not configured.")

    import redis

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    client.ping()
    cleared_count = 0
    batch = []
    for key in client.scan_iter(match="tender:*", count=500):
        batch.append(key)
        if len(batch) == 500:
            cleared_count += client.delete(*batch)
            batch.clear()
    if batch:
        cleared_count += client.delete(*batch)
    logger.info("Cleared %d Redis key(s) matching tender:*.", cleared_count)
    return cleared_count


def tender_decision_summary(new_tender_count):
    return f"Tender scan complete. New tenders found: {new_tender_count}."
