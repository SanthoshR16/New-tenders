import html as html_lib
import os
import time
import threading
import json
import sqlite3
import base64
import urllib.parse
import hashlib
import hmac
import secrets
from functools import wraps
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, session

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "cloud_tenders.db")
AUTHORIZED_ROLES = ("Developer", "Kamal Sir", "Uday Sir")
AUTH_CODE_ENV = {
    "Developer": "DEVELOPER_ACCESS_CODE",
    "Kamal Sir": "KAMAL_SIR_ACCESS_CODE",
    "Uday Sir": "UDAY_SIR_ACCESS_CODE",
}

INITIAL_MANUFACTURERS = [
    "GMPL", "Adonis", "Advantage", "Sysmed", "Appasamy", "Shalya",
    "Mindray", "Sonastar", "Karlkaps", "Mediland", "Medimeas",
    "Smith & Nephew", "Times Surgical", "Timelight", "Bell Surgical",
    "Bistos", "Panacea", "CKK", "Santosh Surgical", "Mr ENGG",
    "IFB", "Cnergy", "Clarity", "Radical", "Pridex", "Swemed", "Anand Agencies"
]

INITIAL_APPROVERS = list(AUTHORIZED_ROLES)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS manufacturers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE COLLATE NOCASE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS approvers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE COLLATE NOCASE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tenders_catalog (
        tender_no TEXT PRIMARY KEY COLLATE NOCASE,
        tender_name TEXT,
        department TEXT,
        items_json TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pending_sync (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type TEXT,
        tender_no TEXT,
        data_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        synced INTEGER DEFAULT 0
    )
    """)
    for m in INITIAL_MANUFACTURERS:
        cur.execute("INSERT OR IGNORE INTO manufacturers (name) VALUES (?)", (m,))
    for a in INITIAL_APPROVERS:
        cur.execute("INSERT OR IGNORE INTO approvers (name) VALUES (?)", (a,))
    conn.commit()
    conn.close()

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Strict",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 365 * 10,
)


def _configured_access_codes():
    codes = {role: os.environ.get(env_name, "").strip() for role, env_name in AUTH_CODE_ENV.items()}
    if any(len(code) < 24 or not code.isascii() for code in codes.values()):
        return None
    return codes


def _configure_session_secret():
    codes = _configured_access_codes()
    if codes:
        material = "\n".join(codes[role] for role in AUTHORIZED_ROLES)
        app.secret_key = hashlib.sha256(("san-tenders-session:" + material).encode("utf-8")).hexdigest()
    else:
        app.secret_key = secrets.token_urlsafe(48)


def _current_member():
    role = session.get("authorized_role")
    return role if role in AUTHORIZED_ROLES else None


def require_member(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _current_member():
            return jsonify({"status": "error", "message": "This device is not authorized."}), 401
        return view(*args, **kwargs)
    return wrapped


def _whatsapp_decision_message(action_type, data):
    tender_no = str(data.get("tender_no") or "")
    tender_name = str(data.get("tender_name") or "")
    approved_by = str(data.get("approved_by") or "")
    if action_type == "BID_ALLOCATION":
        lines = [
            "✅ *BID APPROVED & MANUFACTURER ALLOCATED*",
            "",
            f"📌 *Tender:* {tender_no}"
            + (f" - {tender_name}" if tender_name and tender_name != tender_no else ""),
            f"👤 *Approved By:* {approved_by}",
            "",
            "🏭 *Allocations:*",
        ]
        allocations = data.get("allocations") or []
        if not isinstance(allocations, list):
            raise ValueError("Allocation data must be a list.")
        for allocation in allocations:
            if not isinstance(allocation, dict):
                raise ValueError("Each allocation must be an object.")
            item_name = str(allocation.get("item_name") or "")
            quantity = str(allocation.get("quantity", 1))
            manufacturer = str(allocation.get("manufacturer") or "")
            lines.append(f"  *{item_name}* (Qty: {quantity}) ➔ *{manufacturer}*")
        lines.extend(("", "_Recorded in local system & database._"))
    elif action_type == "NOT_BID":
        lines = [
            "🚫 *TENDER DECISION — NOT BID*",
            "",
            f"📌 *Tender:* {tender_no}"
            + (f" - {tender_name}" if tender_name and tender_name != tender_no else ""),
            "🏢 *Status:* Rejected / Moved to Not Done",
            f"👤 *Decision By:* {approved_by}",
            "",
            "_Recorded in local system & database._",
        ]
    else:
        raise ValueError(f"Unsupported decision type: {action_type!r}")

    message = "\n".join(lines)
    if len(message) > 6000:
        raise ValueError("Decision message is too long to share reliably.")
    return message


AUTH_GATE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>San Tenders — Member Sign In</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #0f172a; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px 16px; -webkit-font-smoothing: antialiased; }
        .card { max-width: 440px; width: 100%; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 30px -5px rgba(15, 23, 42, 0.08), 0 4px 6px -2px rgba(15, 23, 42, 0.03); overflow: hidden; border: 1px solid #e2e8f0; text-align: center; }
        .hdr { background: linear-gradient(135deg, #15803d 0%, #166534 100%); color: #ffffff; padding: 28px 24px; position: relative; }
        .badge { display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.2); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); color: #ffffff; padding: 4px 12px; border-radius: 9999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; border: 1px solid rgba(255,255,255,0.25); margin-bottom: 10px; text-transform: uppercase; }
        .hdr h2 { font-size: 21px; font-weight: 700; color: #ffffff; margin-bottom: 4px; letter-spacing: -0.01em; }
        .hdr p { font-size: 13px; color: rgba(255, 255, 255, 0.88); font-weight: 500; }
        .roles { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
        .role-chip { font-size: 11.5px; font-weight: 600; background: rgba(255,255,255,0.15); color: #ffffff; padding: 3px 10px; border-radius: 9999px; border: 1px solid rgba(255,255,255,0.2); }
        .content { padding: 28px 24px; }
        #status { font-size: 13.5px; color: #475569; line-height: 1.5; margin-bottom: 18px; font-weight: 500; }
        .form-group { text-align: left; margin-bottom: 16px; }
        .form-group label { display: block; font-size: 12.5px; font-weight: 600; color: #334155; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        .input-wrap { position: relative; }
        .input-wrap input { width: 100%; padding: 12px 14px; font-size: 14px; font-family: inherit; border: 1.5px solid #cbd5e1; border-radius: 10px; background: #f8fafc; color: #0f172a; outline: none; transition: all 0.15s ease; }
        .input-wrap input:focus { border-color: #15803d; background: #ffffff; box-shadow: 0 0 0 3px rgba(21, 128, 61, 0.12); }
        .submit-btn { width: 100%; padding: 13px; background: #15803d; color: #ffffff; border: 0; border-radius: 10px; font-size: 14.5px; font-weight: 700; font-family: inherit; cursor: pointer; transition: all 0.15s ease; box-shadow: 0 2px 4px rgba(21, 128, 61, 0.2); }
        .submit-btn:hover:not(:disabled) { background: #166534; transform: translateY(-1px); box-shadow: 0 4px 8px rgba(21, 128, 61, 0.25); }
        .submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .footer-note { margin-top: 16px; font-size: 12px; color: #94a3b8; font-weight: 500; }
    </style>
</head>
<body>
    <main class="card">
        <div class="hdr">
            <div class="badge">🔐 Security Gateway</div>
            <h2>San Tenders</h2>
            <p>Authorized Decision Approvals</p>
            <div class="roles">
                <span class="role-chip">Kamal Sir</span>
                <span class="role-chip">Uday Sir</span>
                <span class="role-chip">Developer</span>
            </div>
        </div>
        <div class="content">
            <p id="status" role="status" aria-live="polite">Checking saved access / credentials…</p>
            <form id="login-form" style="display:none">
                <div class="form-group">
                    <label for="access-code">Enter Member access code</label>
                    <div class="input-wrap">
                        <input id="access-code" type="password" autocomplete="current-password" required minlength="24" placeholder="Paste your 24+ character security code">
                    </div>
                </div>
                <button type="submit" class="submit-btn">Unlock Tender Portal</button>
            </form>
            <div class="footer-note">Protected via End-to-End HMAC Encryption</div>
        </div>
    </main>
    <script>
        let reopeningTender = false;
        let checkingSession = false;
        function showSignIn(message) {
            document.getElementById("status").textContent = message;
            document.getElementById("login-form").style.display = "block";
        }

        async function reopenIfAlreadySignedIn() {
            if (reopeningTender || checkingSession) return;
            checkingSession = true;
            try {
                const response = await fetch("/api/auth/status", {
                    credentials: "same-origin",
                    cache: "no-store"
                });
                const result = await response.json();
                if (response.ok && result.authenticated) {
                    reopeningTender = true;
                    window.location.reload();
                    return;
                }
                showSignIn("Enter your private access code to continue.");
            } catch (error) {
                showSignIn("Could not check saved sign-in. You can still enter your access code.");
            } finally {
                checkingSession = false;
            }
        }

        window.addEventListener("pageshow", reopenIfAlreadySignedIn);
        reopenIfAlreadySignedIn();

        document.getElementById("login-form").addEventListener("submit", async event => {
            event.preventDefault();
            const status = document.getElementById("status");
            const button = event.currentTarget.querySelector("button");
            button.disabled = true;
            button.textContent = "Verifying Access…";
            try {
                const response = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({access_code: document.getElementById("access-code").value}),
                    credentials: "same-origin"
                });
                const result = await response.json();
                if (!response.ok) {
                    status.textContent = result.message || "This access code is invalid.";
                    status.style.color = "#dc2626";
                    button.disabled = false;
                    button.textContent = "Unlock Tender Portal";
                    return;
                }
                status.textContent = "Access confirmed for " + result.role + ". Opening tender…";
                status.style.color = "#15803d";
                window.location.reload();
            } catch (error) {
                status.textContent = "Could not sign in. Check your connection and retry.";
                status.style.color = "#dc2626";
                button.disabled = false;
                button.textContent = "Unlock Tender Portal";
            }
        });
    </script>
</body>
</html>"""


def auth_gate_response():
    response = app.make_response(render_template_string(AUTH_GATE_HTML))
    response.headers["Cache-Control"] = "no-store"
    return response

_configure_session_secret()
init_db()

TENDER_CATALOG = {
    "IND2708": {
        "tender_no": "IND2708",
        "tender_name": "SUPPLY OF CARDIOLOGY CONSUMABLES ITEMS",
        "department": "DHFWS (Shivamogga)",
        "items": [
            {
                "id": 1,
                "code": "LL03",
                "item_name": "P Heat sealing Sterilization flat Reel 150mm 200",
                "quantity": "1"
            },
            {
                "id": 2,
                "code": "LL02",
                "item_name": "M Heat sealing Sterilization flat Reel 400mm 200",
                "quantity": "1"
            },
            {
                "id": 3,
                "code": "LL01",
                "item_name": "H Heat sealing Sterilization flat Reel 250mm 200",
                "quantity": "1"
            }
        ]
    },
    "IND2706": {
        "tender_no": "IND2706",
        "tender_name": "TENDER FOR THE SUPPLY OF EQUIPMENT FOR ALL WARD TO WENLOCK HOSPITAL",
        "department": "DHFWS (Dakshina Kannada)",
        "items": [
            {
                "id": 1,
                "code": "EQPU11",
                "item_name": "Vascular forceps with fine tip 10",
                "quantity": "1"
            },
            {
                "id": 2,
                "code": "EQPU10",
                "item_name": "Vascular forceps with fine tip 8",
                "quantity": "1"
            },
            {
                "id": 3,
                "code": "EQPU09",
                "item_name": "Vascular forceps with fine tip 6",
                "quantity": "1"
            },
            {
                "id": 4,
                "code": "EQPU08",
                "item_name": "Mosquito artery Forceps curved with Fine Tip 5",
                "quantity": "1"
            },
            {
                "id": 5,
                "code": "EQPU07",
                "item_name": "Prolene Needle Holder with fine tip 8",
                "quantity": "1"
            },
            {
                "id": 6,
                "code": "EQPU06",
                "item_name": "Prolene Needle Holder with fine tip 6",
                "quantity": "1"
            },
            {
                "id": 7,
                "code": "EQPU05",
                "item_name": "Maleable Copper retractor",
                "quantity": "1"
            },
            {
                "id": 8,
                "code": "EQPU03",
                "item_name": "Babcock 6",
                "quantity": "1"
            },
            {
                "id": 9,
                "code": "EQPU02",
                "item_name": "Alli s forceps 6 15cm",
                "quantity": "1"
            },
            {
                "id": 10,
                "code": "EQPU01",
                "item_name": "Mosquito Artery Forceps Stright with Fine Tip 5",
                "quantity": "1"
            },
            {
                "id": 11,
                "code": "EQPU37",
                "item_name": "Peristeol Elevator",
                "quantity": "1"
            },
            {
                "id": 12,
                "code": "EQPU36",
                "item_name": "Metal Suction tip size 0",
                "quantity": "1"
            },
            {
                "id": 13,
                "code": "EQPU35",
                "item_name": "Metal Suction tip size 4",
                "quantity": "1"
            },
            {
                "id": 14,
                "code": "EQPU34",
                "item_name": "Metal Suction tip size 3",
                "quantity": "1"
            },
            {
                "id": 15,
                "code": "EQPU33",
                "item_name": "Metal Suction tip size 2",
                "quantity": "1"
            },
            {
                "id": 16,
                "code": "EQPU32",
                "item_name": "Metal Suction tip size 1",
                "quantity": "1"
            },
            {
                "id": 17,
                "code": "EQPU31",
                "item_name": "Adsons Tooth forceps",
                "quantity": "1"
            },
            {
                "id": 18,
                "code": "EQPU30",
                "item_name": "Gally cup medium",
                "quantity": "1"
            },
            {
                "id": 19,
                "code": "EQPU29",
                "item_name": "Rib cutter Adult",
                "quantity": "1"
            },
            {
                "id": 20,
                "code": "EQPU28",
                "item_name": "Angled Vascular Clamps 75 length 16 cm",
                "quantity": "1"
            },
            {
                "id": 21,
                "code": "EQPU27",
                "item_name": "Angled Vascular Clamps 75 length 22 cm",
                "quantity": "1"
            },
            {
                "id": 22,
                "code": "EQPU26",
                "item_name": "Aartic clamps length 22 cm Teflon coated Angled",
                "quantity": "1"
            },
            {
                "id": 23,
                "code": "EQPU25",
                "item_name": "Aartic clamps length 22 cm Teflon coated Stright",
                "quantity": "1"
            },
            {
                "id": 24,
                "code": "EQPU24",
                "item_name": "Half Circle Vascular Clamps length 16 cm",
                "quantity": "1"
            },
            {
                "id": 25,
                "code": "EQPU22",
                "item_name": "Curved Cooly Vascular Clamp length 17cm",
                "quantity": "1"
            },
            {
                "id": 26,
                "code": "EQPU21",
                "item_name": "Satinsky Vascular Clamps angled Length 16cm",
                "quantity": "1"
            },
            {
                "id": 27,
                "code": "EQPU20",
                "item_name": "Satinsky Vascular Clamps angled Length 20cm",
                "quantity": "1"
            },
            {
                "id": 28,
                "code": "EQPU19",
                "item_name": "Satinsky Vascular Clamps angled Length 22cm",
                "quantity": "1"
            },
            {
                "id": 29,
                "code": "EQPU18",
                "item_name": "Satinsky Vascular Clamps angled Length 25cm",
                "quantity": "1"
            },
            {
                "id": 30,
                "code": "EQPU17",
                "item_name": "Vascular Clamps Satinsky Length 26cm",
                "quantity": "1"
            },
            {
                "id": 31,
                "code": "EQPU16",
                "item_name": "Right Angle Forceps 6",
                "quantity": "1"
            },
            {
                "id": 32,
                "code": "EQPU15",
                "item_name": "Right Angle Forceps 8",
                "quantity": "1"
            },
            {
                "id": 33,
                "code": "EQPU14",
                "item_name": "Right Angle Forceps 7",
                "quantity": "1"
            },
            {
                "id": 34,
                "code": "EQPU13",
                "item_name": "Rib aprovimater Paed",
                "quantity": "1"
            },
            {
                "id": 35,
                "code": "EQPU12",
                "item_name": "Rib aprovimater Adult",
                "quantity": "1"
            },
            {
                "id": 36,
                "code": "EQPU62",
                "item_name": "Wire speculum Adult closed type",
                "quantity": "1"
            },
            {
                "id": 37,
                "code": "EQPU61",
                "item_name": "Artery Forceps Straight Long 10",
                "quantity": "1"
            },
            {
                "id": 38,
                "code": "EQPU60",
                "item_name": "S S Small Bin 8 6",
                "quantity": "1"
            },
            {
                "id": 39,
                "code": "EQPU59",
                "item_name": "Artery Forceps Long Straight 8",
                "quantity": "1"
            },
            {
                "id": 40,
                "code": "EQPU58",
                "item_name": "Dessecting Toothed Forceps 6",
                "quantity": "1"
            },
            {
                "id": 41,
                "code": "EQPU57",
                "item_name": "Alice Forceps 8",
                "quantity": "1"
            },
            {
                "id": 42,
                "code": "EQPU56",
                "item_name": "Artery Forceps Straight 6",
                "quantity": "1"
            },
            {
                "id": 43,
                "code": "EQPU55",
                "item_name": "Artery Forceps curved 6",
                "quantity": "1"
            },
            {
                "id": 44,
                "code": "EQPU54",
                "item_name": "Steel Tray Medium 9 6",
                "quantity": "1"
            },
            {
                "id": 45,
                "code": "EQPU53",
                "item_name": "Straight Scissor 8",
                "quantity": "1"
            },
            {
                "id": 46,
                "code": "EQPU52",
                "item_name": "Curved Scissor 8",
                "quantity": "1"
            },
            {
                "id": 47,
                "code": "EQPU51",
                "item_name": "Toothed Forceps Long 10",
                "quantity": "1"
            },
            {
                "id": 48,
                "code": "EQPU50",
                "item_name": "Toothed Forceps Medium 6",
                "quantity": "1"
            },
            {
                "id": 49,
                "code": "EQPU49",
                "item_name": "Needle Holder Medium 8",
                "quantity": "1"
            },
            {
                "id": 50,
                "code": "EQPU48",
                "item_name": "Needle Holder Long 10",
                "quantity": "1"
            },
            {
                "id": 51,
                "code": "EQPU47",
                "item_name": "Artery Forceps Long curved 10",
                "quantity": "1"
            },
            {
                "id": 52,
                "code": "EQPU46",
                "item_name": "Artery Forceps medium curved 8",
                "quantity": "1"
            },
            {
                "id": 53,
                "code": "EQPU45",
                "item_name": "Brain Cannula with blunt tip",
                "quantity": "1"
            },
            {
                "id": 54,
                "code": "EQPU44",
                "item_name": "Desjardins stone holding forceps 9",
                "quantity": "1"
            },
            {
                "id": 55,
                "code": "EQPU43",
                "item_name": "Bone file wooden handle Paed",
                "quantity": "1"
            },
            {
                "id": 56,
                "code": "EQPU42",
                "item_name": "Spine Nibbler Angled 14 5 cm",
                "quantity": "1"
            },
            {
                "id": 57,
                "code": "EQPU41",
                "item_name": "Spine Nibbler Straight 14 5 cm",
                "quantity": "1"
            },
            {
                "id": 58,
                "code": "EQPU40",
                "item_name": "Medzinbaum Scissors 5 Curved",
                "quantity": "1"
            },
            {
                "id": 59,
                "code": "EQPU39",
                "item_name": "Medzinbaum Scissors 5 Straight",
                "quantity": "1"
            },
            {
                "id": 60,
                "code": "EQPU38",
                "item_name": "Deavers Retracter 50 mm wide",
                "quantity": "1"
            },
            {
                "id": 61,
                "code": "EQPU89",
                "item_name": "Sterilization Box 8 4 1 single mat",
                "quantity": "1"
            },
            {
                "id": 62,
                "code": "EQPU88",
                "item_name": "Corneal trephine 6mm 7mm 75mm 8mm",
                "quantity": "1"
            },
            {
                "id": 63,
                "code": "EQPU87",
                "item_name": "Corneal punch",
                "quantity": "1"
            },
            {
                "id": 64,
                "code": "EQPU86",
                "item_name": "Bone punch 1 5mm 2 0mm 25mm",
                "quantity": "1"
            },
            {
                "id": 65,
                "code": "EQPU85",
                "item_name": "Caliper straight",
                "quantity": "1"
            },
            {
                "id": 66,
                "code": "EQPU84",
                "item_name": "Sac Dissector 23G Langs",
                "quantity": "1"
            },
            {
                "id": 67,
                "code": "EQPU83",
                "item_name": "Punctum dilator double ended",
                "quantity": "1"
            },
            {
                "id": 68,
                "code": "EQPU82",
                "item_name": "Pereosteal elevator freer",
                "quantity": "1"
            },
            {
                "id": 69,
                "code": "EQPU81",
                "item_name": "Sinskey Dialor 0 2mm",
                "quantity": "1"
            },
            {
                "id": 70,
                "code": "EQPU80",
                "item_name": "Musclae Hook Grafe",
                "quantity": "1"
            },
            {
                "id": 71,
                "code": "EQPU79",
                "item_name": "Musclae Hook Jameson",
                "quantity": "1"
            },
            {
                "id": 72,
                "code": "EQPU78",
                "item_name": "Vectis serrated",
                "quantity": "1"
            },
            {
                "id": 73,
                "code": "EQPU77",
                "item_name": "Catspaw retractor 4 pongs",
                "quantity": "1"
            },
            {
                "id": 74,
                "code": "EQPU76",
                "item_name": "Catspaw retractor 3 pongs",
                "quantity": "1"
            },
            {
                "id": 75,
                "code": "EQPU75",
                "item_name": "Needle holder straight",
                "quantity": "1"
            },
            {
                "id": 76,
                "code": "EQPU74",
                "item_name": "Needle holder curved 8 0",
                "quantity": "1"
            },
            {
                "id": 77,
                "code": "EQPU73",
                "item_name": "Corneal scissor 11mm curved blade",
                "quantity": "1"
            },
            {
                "id": 78,
                "code": "EQPU72",
                "item_name": "Vannas scissor 11mm blade straight",
                "quantity": "1"
            },
            {
                "id": 79,
                "code": "EQPU71",
                "item_name": "Vannas scissor 5mm blade straight",
                "quantity": "1"
            },
            {
                "id": 80,
                "code": "EQPU69",
                "item_name": "Lens holding forceps Daljit",
                "quantity": "1"
            },
            {
                "id": 81,
                "code": "EQPU68",
                "item_name": "St Martin forceps",
                "quantity": "1"
            },
            {
                "id": 82,
                "code": "EQPU67",
                "item_name": "Colibre Barraquer Corneal forceps",
                "quantity": "1"
            },
            {
                "id": 83,
                "code": "EQPU66",
                "item_name": "Suture tier curved",
                "quantity": "1"
            },
            {
                "id": 84,
                "code": "EQPU65",
                "item_name": "Superoir rectus forceps",
                "quantity": "1"
            },
            {
                "id": 85,
                "code": "EQPU63",
                "item_name": "Wire speculum Paediatric closed type",
                "quantity": "1"
            },
            {
                "id": 86,
                "code": "EQPU95",
                "item_name": "Seissor Curved",
                "quantity": "1"
            },
            {
                "id": 87,
                "code": "EQPU94",
                "item_name": "Curved Artery forceps",
                "quantity": "1"
            },
            {
                "id": 88,
                "code": "EQPU93",
                "item_name": "Stright Artery forceps",
                "quantity": "1"
            },
            {
                "id": 89,
                "code": "EQPU92",
                "item_name": "SSTray with lid Small",
                "quantity": "1"
            },
            {
                "id": 90,
                "code": "EQPU91",
                "item_name": "S S Tray with Lid Medium",
                "quantity": "1"
            },
            {
                "id": 91,
                "code": "EQPU90",
                "item_name": "Sterilization Box 8 4 2 double mat",
                "quantity": "1"
            },
            {
                "id": 92,
                "code": "EQPU119",
                "item_name": "Deaver Retractor 10mm Wide",
                "quantity": "1"
            },
            {
                "id": 93,
                "code": "EQPU118",
                "item_name": "Deaver Retractor 75mm Wide",
                "quantity": "1"
            },
            {
                "id": 94,
                "code": "EQPU117",
                "item_name": "Doyen Retractor Bigger",
                "quantity": "1"
            },
            {
                "id": 95,
                "code": "EQPU116",
                "item_name": "Alice Forceps Long",
                "quantity": "1"
            },
            {
                "id": 96,
                "code": "EQPU115",
                "item_name": "Stepler removal",
                "quantity": "1"
            },
            {
                "id": 97,
                "code": "EQPU114",
                "item_name": "Oxygen Key",
                "quantity": "1"
            },
            {
                "id": 98,
                "code": "EQPU113",
                "item_name": "Back Rest",
                "quantity": "1"
            },
            {
                "id": 99,
                "code": "EQPU112",
                "item_name": "Cusion Chairs",
                "quantity": "1"
            },
            {
                "id": 100,
                "code": "EQPU111",
                "item_name": "B M W Peddic Bin Black Small",
                "quantity": "1"
            },
            {
                "id": 101,
                "code": "EQPU110",
                "item_name": "Stainless steel Bin Small",
                "quantity": "1"
            },
            {
                "id": 102,
                "code": "EQPU109",
                "item_name": "Kidney Tray Size 8",
                "quantity": "1"
            },
            {
                "id": 103,
                "code": "EQPU108",
                "item_name": "Suction Apparator",
                "quantity": "1"
            },
            {
                "id": 104,
                "code": "EQPU107",
                "item_name": "SS Dressing Tray with lid Medium",
                "quantity": "1"
            },
            {
                "id": 105,
                "code": "EQPU106",
                "item_name": "S S Dressing Bins small",
                "quantity": "1"
            },
            {
                "id": 106,
                "code": "EQPU105",
                "item_name": "Chittle forceps",
                "quantity": "1"
            },
            {
                "id": 107,
                "code": "EQPU104",
                "item_name": "Scissor Straight 6 inch",
                "quantity": "1"
            },
            {
                "id": 108,
                "code": "EQPU103",
                "item_name": "B P Handle 6 inch",
                "quantity": "1"
            },
            {
                "id": 109,
                "code": "EQPU102",
                "item_name": "Suture Removal Scissor 6",
                "quantity": "1"
            },
            {
                "id": 110,
                "code": "EQPU101",
                "item_name": "Stainless steel Stillet for ET Tube",
                "quantity": "1"
            },
            {
                "id": 111,
                "code": "EQPU144",
                "item_name": "Bone Cutter Large",
                "quantity": "1"
            },
            {
                "id": 112,
                "code": "EQPU143",
                "item_name": "Bone Cutter Medium",
                "quantity": "1"
            },
            {
                "id": 113,
                "code": "EQPU142",
                "item_name": "Bone Nibbler Double Action Large",
                "quantity": "1"
            },
            {
                "id": 114,
                "code": "EQPU141",
                "item_name": "Bone Nibbler Double Action Medium",
                "quantity": "1"
            },
            {
                "id": 115,
                "code": "EQPU140",
                "item_name": "Bone Nibbler Curved",
                "quantity": "1"
            },
            {
                "id": 116,
                "code": "EQPU139",
                "item_name": "Bone Nibbler Straight",
                "quantity": "1"
            },
            {
                "id": 117,
                "code": "EQPU138",
                "item_name": "Babcock forceps Large",
                "quantity": "1"
            },
            {
                "id": 118,
                "code": "EQPU137",
                "item_name": "Babcock forceps Medium",
                "quantity": "1"
            },
            {
                "id": 119,
                "code": "EQPU136",
                "item_name": "Wire Passer Large",
                "quantity": "1"
            },
            {
                "id": 120,
                "code": "EQPU135",
                "item_name": "Wire Passer Medium",
                "quantity": "1"
            },
            {
                "id": 121,
                "code": "EQPU134",
                "item_name": "Lanes Bone Elevator",
                "quantity": "1"
            },
            {
                "id": 122,
                "code": "EQPU133",
                "item_name": "Cobbs 30mm",
                "quantity": "1"
            },
            {
                "id": 123,
                "code": "EQPU132",
                "item_name": "Cobbs 26mm",
                "quantity": "1"
            },
            {
                "id": 124,
                "code": "EQPU131",
                "item_name": "Bone Lever Narrow Tip 240mm",
                "quantity": "1"
            },
            {
                "id": 125,
                "code": "EQPU130",
                "item_name": "Bone Lever Long Length 240mm",
                "quantity": "1"
            },
            {
                "id": 126,
                "code": "EQPU129",
                "item_name": "Hohmann Retractors 18mm Wide",
                "quantity": "1"
            },
            {
                "id": 127,
                "code": "EQPU128",
                "item_name": "Bristow",
                "quantity": "1"
            },
            {
                "id": 128,
                "code": "EQPU127",
                "item_name": "Forearm Bone Elevator",
                "quantity": "1"
            },
            {
                "id": 129,
                "code": "EQPU126",
                "item_name": "Blade Size 70 14mm",
                "quantity": "1"
            },
            {
                "id": 130,
                "code": "EQPU125",
                "item_name": "Blade Size 40 11mm",
                "quantity": "1"
            },
            {
                "id": 131,
                "code": "EQPU124",
                "item_name": "Langer Back Retractor Medium 1 5",
                "quantity": "1"
            },
            {
                "id": 132,
                "code": "EQPU123",
                "item_name": "Langer Back Retractor Medium 1",
                "quantity": "1"
            },
            {
                "id": 133,
                "code": "EQPU122",
                "item_name": "Langer Back Retractor Medium 3 4",
                "quantity": "1"
            },
            {
                "id": 134,
                "code": "EQPU121",
                "item_name": "Langer Back Retractor Medium 1 2",
                "quantity": "1"
            },
            {
                "id": 135,
                "code": "EQPU120",
                "item_name": "Langer Back Retractor Medium 1 4",
                "quantity": "1"
            },
            {
                "id": 136,
                "code": "EQPU169",
                "item_name": "Seissores Curved small size 4 6",
                "quantity": "1"
            },
            {
                "id": 137,
                "code": "EQPU168",
                "item_name": "Seissores Curved metzenbaum",
                "quantity": "1"
            },
            {
                "id": 138,
                "code": "EQPU167",
                "item_name": "Medium Bin 12 9 12 10",
                "quantity": "1"
            },
            {
                "id": 139,
                "code": "EQPU166",
                "item_name": "Trocher Laproscopic Canula 5mm",
                "quantity": "1"
            },
            {
                "id": 140,
                "code": "EQPU165",
                "item_name": "Trocher Laproscopic Canula 10mm",
                "quantity": "1"
            },
            {
                "id": 141,
                "code": "EQPU164",
                "item_name": "Micro Scissor",
                "quantity": "1"
            },
            {
                "id": 142,
                "code": "EQPU163",
                "item_name": "Atruomatic Grasper",
                "quantity": "1"
            },
            {
                "id": 143,
                "code": "EQPU162",
                "item_name": "Bowel Grasper",
                "quantity": "1"
            },
            {
                "id": 144,
                "code": "EQPU161",
                "item_name": "Monopolar Mary Land",
                "quantity": "1"
            },
            {
                "id": 145,
                "code": "EQPU160",
                "item_name": "Biopolar Mary Land with Cord",
                "quantity": "1"
            },
            {
                "id": 146,
                "code": "EQPU159",
                "item_name": "Carbide Drill Bit set",
                "quantity": "1"
            },
            {
                "id": 147,
                "code": "EQPU158",
                "item_name": "Hollow Mill for bone screw removal set",
                "quantity": "1"
            },
            {
                "id": 148,
                "code": "EQPU157",
                "item_name": "Saw with Electrical Cable",
                "quantity": "1"
            },
            {
                "id": 149,
                "code": "EQPU156",
                "item_name": "Two pointed reduction clamps Fenur Tibia Patella Redius",
                "quantity": "1"
            },
            {
                "id": 150,
                "code": "EQPU155",
                "item_name": "Mipo Minimal invasive Percutaneous osteosynthesis Instruments",
                "quantity": "1"
            },
            {
                "id": 151,
                "code": "EQPU154",
                "item_name": "B.P.Handle 4 No",
                "quantity": "1"
            },
            {
                "id": 152,
                "code": "EQPU153",
                "item_name": "Steal basin small",
                "quantity": "1"
            },
            {
                "id": 153,
                "code": "EQPU152",
                "item_name": "Non Toothed Forceps long",
                "quantity": "1"
            },
            {
                "id": 154,
                "code": "EQPU151",
                "item_name": "Adson Non Toothed Forceps",
                "quantity": "1"
            },
            {
                "id": 155,
                "code": "EQPU150",
                "item_name": "Single Hook Retractor",
                "quantity": "1"
            },
            {
                "id": 156,
                "code": "EQPU149",
                "item_name": "Catspaw Retractor Double Hook",
                "quantity": "1"
            },
            {
                "id": 157,
                "code": "EQPU148",
                "item_name": "Catspaw Retractor Single Hook",
                "quantity": "1"
            },
            {
                "id": 158,
                "code": "EQPU147",
                "item_name": "Bone Holding For Femur",
                "quantity": "1"
            },
            {
                "id": 159,
                "code": "EQPU146",
                "item_name": "Plate Holding For Femur Bone",
                "quantity": "1"
            },
            {
                "id": 160,
                "code": "EQPU145",
                "item_name": "Bone Hammer Orthopeadic Fibre Handle",
                "quantity": "1"
            },
            {
                "id": 161,
                "code": "EQPU196",
                "item_name": "Laproscopic Hasson Trocer",
                "quantity": "1"
            },
            {
                "id": 162,
                "code": "EQPU195",
                "item_name": "Verress Needle",
                "quantity": "1"
            },
            {
                "id": 163,
                "code": "EQPU194",
                "item_name": "Lap clips size 500",
                "quantity": "1"
            },
            {
                "id": 164,
                "code": "EQPU193",
                "item_name": "Lap clips size 400",
                "quantity": "1"
            },
            {
                "id": 165,
                "code": "EQPU192",
                "item_name": "Lap clips size 300",
                "quantity": "1"
            },
            {
                "id": 166,
                "code": "EQPU191",
                "item_name": "Laproscopic Clip applicator 10mm",
                "quantity": "1"
            },
            {
                "id": 167,
                "code": "EQPU190",
                "item_name": "Laproscopic Clip applicator 5mm",
                "quantity": "1"
            },
            {
                "id": 168,
                "code": "EQPU189",
                "item_name": "Laproscopic Stone holding forceps",
                "quantity": "1"
            },
            {
                "id": 169,
                "code": "EQPU188",
                "item_name": "Bowel Curved Graspers",
                "quantity": "1"
            },
            {
                "id": 170,
                "code": "EQPU186",
                "item_name": "Biopolar maryland with cable",
                "quantity": "1"
            },
            {
                "id": 171,
                "code": "EQPU185",
                "item_name": "Vizi Ports",
                "quantity": "1"
            },
            {
                "id": 172,
                "code": "EQPU184",
                "item_name": "mm Ports 5",
                "quantity": "1"
            },
            {
                "id": 173,
                "code": "EQPU183",
                "item_name": "mm Ports10",
                "quantity": "1"
            },
            {
                "id": 174,
                "code": "EQPU182",
                "item_name": "Suction Bottle",
                "quantity": "1"
            },
            {
                "id": 175,
                "code": "EQPU181",
                "item_name": "Total Oxygen Humidifier without Probe",
                "quantity": "1"
            },
            {
                "id": 176,
                "code": "EQPU180",
                "item_name": "Total Oxygen Humidifier with Probe",
                "quantity": "1"
            },
            {
                "id": 177,
                "code": "EQPU179",
                "item_name": "Total Suction BS Probe",
                "quantity": "1"
            },
            {
                "id": 178,
                "code": "EQPU178",
                "item_name": "Total Oxygen BS Probe",
                "quantity": "1"
            },
            {
                "id": 179,
                "code": "EQPU177",
                "item_name": "Total Suction Din Probe",
                "quantity": "1"
            },
            {
                "id": 180,
                "code": "EQPU176",
                "item_name": "Total Oxygen Din Pribe",
                "quantity": "1"
            },
            {
                "id": 181,
                "code": "EQPU175",
                "item_name": "Oxygen Trolly",
                "quantity": "1"
            },
            {
                "id": 182,
                "code": "EQPU174",
                "item_name": "Scoop or Curator",
                "quantity": "1"
            },
            {
                "id": 183,
                "code": "EQPU173",
                "item_name": "Transferent ProctoscopePlastic",
                "quantity": "1"
            },
            {
                "id": 184,
                "code": "EQPU172",
                "item_name": "Intestinal Clamps Crussing Bowel",
                "quantity": "1"
            },
            {
                "id": 185,
                "code": "EQPU170",
                "item_name": "Seissoresstraight Mayo",
                "quantity": "1"
            },
            {
                "id": 186,
                "code": "EQPU221",
                "item_name": "Radio Frequency ward",
                "quantity": "1"
            },
            {
                "id": 187,
                "code": "EQPU220",
                "item_name": "Bird beak for for Shoulder Arthroscopy",
                "quantity": "1"
            },
            {
                "id": 188,
                "code": "EQPU219",
                "item_name": "Portals Cannulas 6mm 8mm for Shoulder Arthroscopy",
                "quantity": "1"
            },
            {
                "id": 189,
                "code": "EQPU218",
                "item_name": "Wissinger Rod & Arthroscopic Tissue grasper for shoulder",
                "quantity": "1"
            },
            {
                "id": 190,
                "code": "EQPU217",
                "item_name": "Meniscal punch for Arthroscopy",
                "quantity": "1"
            },
            {
                "id": 191,
                "code": "EQPU216",
                "item_name": "Shaver Blades for Arthroscopy",
                "quantity": "1"
            },
            {
                "id": 192,
                "code": "EQPU215",
                "item_name": "Suture Retriever for Shoulder Arthroscopy",
                "quantity": "1"
            },
            {
                "id": 193,
                "code": "EQPU214",
                "item_name": "mm Suction 10",
                "quantity": "1"
            },
            {
                "id": 194,
                "code": "EQPU213",
                "item_name": "Needle Aspirator",
                "quantity": "1"
            },
            {
                "id": 195,
                "code": "EQPU212",
                "item_name": "Monopolar Hook with Cable",
                "quantity": "1"
            },
            {
                "id": 196,
                "code": "EQPU211",
                "item_name": "Hemolock Clip 5mm 10mm",
                "quantity": "1"
            },
            {
                "id": 197,
                "code": "EQPU210",
                "item_name": "Hemolock Clip Applicator",
                "quantity": "1"
            },
            {
                "id": 198,
                "code": "EQPU209",
                "item_name": "Laproscopic Tranfarcial needle for Suturing",
                "quantity": "1"
            },
            {
                "id": 199,
                "code": "EQPU208",
                "item_name": "Lap Scaler with Cutter",
                "quantity": "1"
            },
            {
                "id": 200,
                "code": "EQPU207",
                "item_name": "Biclamp",
                "quantity": "1"
            },
            {
                "id": 201,
                "code": "EQPU206",
                "item_name": "Biopolar Shearer",
                "quantity": "1"
            },
            {
                "id": 202,
                "code": "EQPU205",
                "item_name": "Uterine Monipulator",
                "quantity": "1"
            },
            {
                "id": 203,
                "code": "EQPU204",
                "item_name": "Babcock Grasper",
                "quantity": "1"
            },
            {
                "id": 204,
                "code": "EQPU203",
                "item_name": "Toothed Grasper",
                "quantity": "1"
            },
            {
                "id": 205,
                "code": "EQPU202",
                "item_name": "Non Toothed Grasper",
                "quantity": "1"
            },
            {
                "id": 206,
                "code": "EQPU201",
                "item_name": "Allis Grasper",
                "quantity": "1"
            },
            {
                "id": 207,
                "code": "EQPU200",
                "item_name": "Alligator Grasper",
                "quantity": "1"
            },
            {
                "id": 208,
                "code": "EQPU199",
                "item_name": "Liner Retractor",
                "quantity": "1"
            },
            {
                "id": 209,
                "code": "EQPU198",
                "item_name": "Laproscopic Fundus Holding Forceps",
                "quantity": "1"
            },
            {
                "id": 210,
                "code": "EQPU197",
                "item_name": "Curved Scissor wth Monopolar Scissor",
                "quantity": "1"
            },
            {
                "id": 211,
                "code": "EQPU254",
                "item_name": "Telescope 70",
                "quantity": "1"
            },
            {
                "id": 212,
                "code": "EQPU253",
                "item_name": "Telescope O",
                "quantity": "1"
            },
            {
                "id": 213,
                "code": "EQPU252",
                "item_name": "PCNL Amplove 22 24 28 cool Company",
                "quantity": "1"
            },
            {
                "id": 214,
                "code": "EQPU251",
                "item_name": "PCNL metal dilators 21 to 30 size",
                "quantity": "1"
            },
            {
                "id": 215,
                "code": "EQPU250",
                "item_name": "Lone Star Retractor",
                "quantity": "1"
            },
            {
                "id": 216,
                "code": "EQPU249",
                "item_name": "Access Sheath 45 cm",
                "quantity": "1"
            },
            {
                "id": 217,
                "code": "EQPU248",
                "item_name": "Access Sheath 35 cm",
                "quantity": "1"
            },
            {
                "id": 218,
                "code": "EQPU247",
                "item_name": "Ring retractor",
                "quantity": "1"
            },
            {
                "id": 219,
                "code": "EQPU246",
                "item_name": "Toomey Syringe 100 ml Blader wash Syringe",
                "quantity": "1"
            },
            {
                "id": 220,
                "code": "EQPU245",
                "item_name": "Richerd Wolf TURP Set",
                "quantity": "1"
            },
            {
                "id": 221,
                "code": "EQPU244",
                "item_name": "Karl Storz Sheet 17F",
                "quantity": "1"
            },
            {
                "id": 222,
                "code": "EQPU243",
                "item_name": "Light Guide Cable 2 8 mm comapible for olympus Scopy Machine",
                "quantity": "1"
            },
            {
                "id": 223,
                "code": "EQPU242",
                "item_name": "flow meter O2",
                "quantity": "1"
            },
            {
                "id": 224,
                "code": "EQPU241",
                "item_name": "Bin Probe with central Oxygen flow meter",
                "quantity": "1"
            },
            {
                "id": 225,
                "code": "EQPU239",
                "item_name": "Stainless Steel bin medium",
                "quantity": "1"
            },
            {
                "id": 226,
                "code": "EQPU238",
                "item_name": "Stainless Steel bin big",
                "quantity": "1"
            },
            {
                "id": 227,
                "code": "EQPU237",
                "item_name": "Stainless Steel Tray medium",
                "quantity": "1"
            },
            {
                "id": 228,
                "code": "EQPU236",
                "item_name": "Kidney Tray medium",
                "quantity": "1"
            },
            {
                "id": 229,
                "code": "EQPU230",
                "item_name": "Artery Forceps Curved 6 inch",
                "quantity": "1"
            },
            {
                "id": 230,
                "code": "EQPU229",
                "item_name": "Spine Board",
                "quantity": "1"
            },
            {
                "id": 231,
                "code": "EQPU228",
                "item_name": "Ring Cutter Large size",
                "quantity": "1"
            },
            {
                "id": 232,
                "code": "EQPU227",
                "item_name": "Hartman s Alligator Forceps",
                "quantity": "1"
            },
            {
                "id": 233,
                "code": "EQPU226",
                "item_name": "Toungu Depressor",
                "quantity": "1"
            },
            {
                "id": 234,
                "code": "EQPU225",
                "item_name": "Nasal Speculam",
                "quantity": "1"
            },
            {
                "id": 235,
                "code": "EQPU223",
                "item_name": "Electric Coil 2K",
                "quantity": "1"
            },
            {
                "id": 236,
                "code": "EQPU99",
                "item_name": "Sponge Holding forceps j",
                "quantity": "1"
            },
            {
                "id": 237,
                "code": "EQPU98",
                "item_name": "Kidney Tray small j",
                "quantity": "1"
            },
            {
                "id": 238,
                "code": "EQPU97",
                "item_name": "Non Toothed forceps 6 inch j",
                "quantity": "1"
            },
            {
                "id": 239,
                "code": "EQPU96",
                "item_name": "Toothed forceps j",
                "quantity": "1"
            },
            {
                "id": 240,
                "code": "EQPU70",
                "item_name": "Bull dog clamp J",
                "quantity": "1"
            },
            {
                "id": 241,
                "code": "EQPU64",
                "item_name": "Kalt needle holder J",
                "quantity": "1"
            },
            {
                "id": 242,
                "code": "EQPU258",
                "item_name": "Thunder beat Tran Compatible for Olympus Thunder Beat",
                "quantity": "1"
            },
            {
                "id": 243,
                "code": "EQPU257",
                "item_name": "Thunder beat Forceps 5mm 35c Compatible for Olympus Thunder Beat",
                "quantity": "1"
            },
            {
                "id": 244,
                "code": "EQPU256",
                "item_name": "Trolly O2 Flow meter with guage",
                "quantity": "1"
            },
            {
                "id": 245,
                "code": "EQPU255",
                "item_name": "Torch j",
                "quantity": "1"
            },
            {
                "id": 246,
                "code": "EQPU240",
                "item_name": "Stainless Steel bin Small j",
                "quantity": "1"
            },
            {
                "id": 247,
                "code": "EQPU235",
                "item_name": "Kidney Tray big j",
                "quantity": "1"
            },
            {
                "id": 248,
                "code": "EQPU234",
                "item_name": "Mosquito Forceps Curved j",
                "quantity": "1"
            },
            {
                "id": 249,
                "code": "EQPU233",
                "item_name": "Toothed Forceps j AA",
                "quantity": "1"
            },
            {
                "id": 250,
                "code": "EQPU232",
                "item_name": "Scissor s Straight",
                "quantity": "1"
            },
            {
                "id": 251,
                "code": "EQPU231",
                "item_name": "Needle Holder 6 inch j",
                "quantity": "1"
            },
            {
                "id": 252,
                "code": "EQPU23",
                "item_name": "Half Circle Vascular Clamps length 23 cm J",
                "quantity": "1"
            },
            {
                "id": 253,
                "code": "EQPU224",
                "item_name": "Skin Traction Set j",
                "quantity": "1"
            },
            {
                "id": 254,
                "code": "EQPU222",
                "item_name": "Arthroscopy Inflow and out Flow Tube Set 10k R a AA",
                "quantity": "1"
            },
            {
                "id": 255,
                "code": "EQPU187",
                "item_name": "Needle Holder j",
                "quantity": "1"
            },
            {
                "id": 256,
                "code": "EQPU171",
                "item_name": "Towel clips j",
                "quantity": "1"
            },
            {
                "id": 257,
                "code": "EQPU100",
                "item_name": "I V Stand j",
                "quantity": "1"
            },
            {
                "id": 258,
                "code": "EQPU04",
                "item_name": "Needle Holder 6 J",
                "quantity": "1"
            }
        ]
    },
    "IND2705": {
        "tender_no": "IND2705",
        "tender_name": "PROCUREMENT OF LABORATORY REQUIREMENTS TO CHC HALEBEEDU",
        "department": "DHFWS (Hassan)",
        "items": [
            {
                "id": 1,
                "code": "CHCHBDLAB104",
                "item_name": "TORNIQUITEETORNIQUITEE",
                "quantity": "1"
            },
            {
                "id": 2,
                "code": "CHCHBDLAB103",
                "item_name": "NITRILE GLOVES M SIZEE",
                "quantity": "1"
            },
            {
                "id": 3,
                "code": "CHCHBDLAB102",
                "item_name": "EXAMINATION GLOVESS M SIZEE",
                "quantity": "1"
            },
            {
                "id": 4,
                "code": "CHCHBDLAB101",
                "item_name": "SANITARY PADDSS",
                "quantity": "1"
            },
            {
                "id": 5,
                "code": "CHCHBDLAB100",
                "item_name": "NORMAL DELIVERY KITT",
                "quantity": "1"
            },
            {
                "id": 6,
                "code": "CHCHBDLAB99",
                "item_name": "DISPOSABLLEE BED SHEETT",
                "quantity": "1"
            },
            {
                "id": 7,
                "code": "CHCHBDLAB98",
                "item_name": "SURGICAL HEAD CAPP SPRING TYPEE",
                "quantity": "1"
            },
            {
                "id": 8,
                "code": "CHCHBDLAB97",
                "item_name": "N 95 Maskss",
                "quantity": "1"
            },
            {
                "id": 9,
                "code": "CHCHBDLAB96",
                "item_name": "TRIPLE LAYER MASK ELASTIC TYPE",
                "quantity": "1"
            },
            {
                "id": 10,
                "code": "CHCHBDLAB95",
                "item_name": "BIOMEDIICAL BAGG GREENN 28 X34--",
                "quantity": "1"
            },
            {
                "id": 11,
                "code": "CHCHBDLAB94",
                "item_name": "BIOMEDICAAL BAGG GREENN 22X24--",
                "quantity": "1"
            },
            {
                "id": 12,
                "code": "CHCHBDLAB93",
                "item_name": "BIOMEDIICAL BAGG REDD 22X24--",
                "quantity": "1"
            },
            {
                "id": 13,
                "code": "CHCHBDLAB92",
                "item_name": "BIIOMEDICAL BAGG BLUEE 22X24--",
                "quantity": "1"
            },
            {
                "id": 14,
                "code": "CHCHBDLAB91",
                "item_name": "BIOMEDICALL BAGG YELLLOWW 22X24--",
                "quantity": "1"
            },
            {
                "id": 15,
                "code": "CHCHBDLAB90",
                "item_name": "FIXERR",
                "quantity": "1"
            },
            {
                "id": 16,
                "code": "CHCHBDLAB89",
                "item_name": "DEVELOPERR",
                "quantity": "1"
            },
            {
                "id": 17,
                "code": "CHCHBDLAB88",
                "item_name": "X-RAY FILM 10/8 GREEN SENSITIVE",
                "quantity": "1"
            },
            {
                "id": 18,
                "code": "CHCHBDLAB87",
                "item_name": "X-RAY FILM 10/12 GREEN SENSITIVE",
                "quantity": "1"
            },
            {
                "id": 19,
                "code": "CHCHBDLAB86",
                "item_name": "X-RAY FILM 12/15 GREEN SENSITIVE",
                "quantity": "1"
            },
            {
                "id": 20,
                "code": "CHCHBDLAB85",
                "item_name": "LANCETT",
                "quantity": "1"
            },
            {
                "id": 21,
                "code": "CHCHBDLAB84",
                "item_name": "LIQUID PARRIFIN OIL",
                "quantity": "1"
            },
            {
                "id": 22,
                "code": "CHCHBDLAB83",
                "item_name": "WINCHESTER BOTTLE",
                "quantity": "1"
            },
            {
                "id": 23,
                "code": "CHCHBDLAB82",
                "item_name": "SLIDE STAINING STAND",
                "quantity": "1"
            },
            {
                "id": 24,
                "code": "CHCHBDLAB81",
                "item_name": "MAC CARTEENEY BOTTLE",
                "quantity": "1"
            },
            {
                "id": 25,
                "code": "CHCHBDLAB80",
                "item_name": "TEST TUBE RAACK",
                "quantity": "1"
            },
            {
                "id": 26,
                "code": "CHCHBDLAB79",
                "item_name": "SLIDE DRING STAND",
                "quantity": "1"
            },
            {
                "id": 27,
                "code": "CHCHBDLAB78",
                "item_name": "DROPPER BOTTLEE",
                "quantity": "1"
            },
            {
                "id": 28,
                "code": "CHCHBDLAB77",
                "item_name": "RAPID TEST CASSETTE FECES",
                "quantity": "1"
            },
            {
                "id": 29,
                "code": "CHCHBDLAB76",
                "item_name": "TROPONIN 1",
                "quantity": "1"
            },
            {
                "id": 30,
                "code": "CHCHBDLAB75",
                "item_name": "DISTRILL WATER",
                "quantity": "1"
            },
            {
                "id": 31,
                "code": "CHCHBDLAB74",
                "item_name": "SALICYLIC ACIDD",
                "quantity": "1"
            },
            {
                "id": 32,
                "code": "CHCHBDLAB73",
                "item_name": "FOUCHETS REAGENTT",
                "quantity": "1"
            },
            {
                "id": 33,
                "code": "CHCHBDLAB72",
                "item_name": "BARRIUM CHLORIDE",
                "quantity": "1"
            },
            {
                "id": 34,
                "code": "CHCHBDLAB71",
                "item_name": "URINE ANALYSIS STRIP",
                "quantity": "1"
            },
            {
                "id": 35,
                "code": "CHCHBDLAB70",
                "item_name": "URINE SUGER SINGLE",
                "quantity": "1"
            },
            {
                "id": 36,
                "code": "CHCHBDLAB69",
                "item_name": "U KETONE BODIES STRIP",
                "quantity": "1"
            },
            {
                "id": 37,
                "code": "CHCHBDLAB68",
                "item_name": "HIV CARD",
                "quantity": "1"
            },
            {
                "id": 38,
                "code": "CHCHBDLAB67",
                "item_name": "HCV CARD",
                "quantity": "1"
            },
            {
                "id": 39,
                "code": "CHCHBDLAB66",
                "item_name": "URIN MICROSCOPY COVER SLIP",
                "quantity": "1"
            },
            {
                "id": 40,
                "code": "CHCHBDLAB65",
                "item_name": "CALCIUM ERBA",
                "quantity": "1"
            },
            {
                "id": 41,
                "code": "CHCHBDLAB64",
                "item_name": "GLASS SLIDE",
                "quantity": "1"
            },
            {
                "id": 42,
                "code": "CHCHBDLAB63",
                "item_name": "APTT--",
                "quantity": "1"
            },
            {
                "id": 43,
                "code": "CHCHBDLAB62",
                "item_name": "PT ERBA",
                "quantity": "1"
            },
            {
                "id": 44,
                "code": "CHCHBDLAB61",
                "item_name": "HBA1C--",
                "quantity": "1"
            },
            {
                "id": 45,
                "code": "CHCHBDLAB60",
                "item_name": "THYROID STIMULITY HARMONE",
                "quantity": "1"
            },
            {
                "id": 46,
                "code": "CHCHBDLAB59",
                "item_name": "THYROID PROFILE 4- T4",
                "quantity": "1"
            },
            {
                "id": 47,
                "code": "CHCHBDLAB58",
                "item_name": "T3",
                "quantity": "1"
            },
            {
                "id": 48,
                "code": "CHCHBDLAB57",
                "item_name": "GAMA GT ERBA",
                "quantity": "1"
            },
            {
                "id": 49,
                "code": "CHCHBDLAB56",
                "item_name": "ELECTROLYTES CONTROL",
                "quantity": "1"
            },
            {
                "id": 50,
                "code": "CHCHBDLAB55",
                "item_name": "ELECTROLYTES CELL WASHER",
                "quantity": "1"
            },
            {
                "id": 51,
                "code": "CHCHBDLAB54",
                "item_name": "ERBA QC NORMO",
                "quantity": "1"
            },
            {
                "id": 52,
                "code": "CHCHBDLAB53",
                "item_name": "STERILE DIISPOOSABLE GLOUSE SIZE 7.5 1X10--",
                "quantity": "1"
            },
            {
                "id": 53,
                "code": "CHCHBDLAB52",
                "item_name": "STERILE DISPOSABLLE GLOWSE SIIZE 7 1X10--",
                "quantity": "1"
            },
            {
                "id": 54,
                "code": "CHCHBDLAB51",
                "item_name": "STERIILE DISPOSABLE GLOUSE SIIZE 6.5 1X10--",
                "quantity": "1"
            },
            {
                "id": 55,
                "code": "CHCHBDLAB50",
                "item_name": "STERILE DISPOSABLEE GLOUSE SIIZE 6 1X10--",
                "quantity": "1"
            },
            {
                "id": 56,
                "code": "CHCHBDLAB49",
                "item_name": "STERIL DISPOSsIBLE SYRIING 10ml 18G 1X50--",
                "quantity": "1"
            },
            {
                "id": 57,
                "code": "CHCHBDLAB48",
                "item_name": "STERIIL DISPOSIBLE SYRIING 5ml 23G 1X100--",
                "quantity": "1"
            },
            {
                "id": 58,
                "code": "CHCHBDLAB47",
                "item_name": "STERIL DISPOSsIBLE SYRIING 2ml 23G 1X100--",
                "quantity": "1"
            },
            {
                "id": 59,
                "code": "CHCHBDLAB46",
                "item_name": "ELETROLYTEE REAGENTT ST 200--",
                "quantity": "1"
            },
            {
                "id": 60,
                "code": "CHCHBDLAB45",
                "item_name": "CRP EERBAA--",
                "quantity": "1"
            },
            {
                "id": 61,
                "code": "CHCHBDLAB44",
                "item_name": "ASLO KIITT--",
                "quantity": "1"
            },
            {
                "id": 62,
                "code": "CHCHBDLAB43",
                "item_name": "R A KIITT--",
                "quantity": "1"
            },
            {
                "id": 63,
                "code": "CHCHBDLAB42",
                "item_name": "erbaa washH--",
                "quantity": "1"
            },
            {
                "id": 64,
                "code": "CHCHBDLAB41",
                "item_name": "MP KITT ABBOTTT 30 T--",
                "quantity": "1"
            },
            {
                "id": 65,
                "code": "CHCHBDLAB40",
                "item_name": "VDRL SYPHIILLIS KITT --",
                "quantity": "1"
            },
            {
                "id": 66,
                "code": "CHCHBDLAB39",
                "item_name": "SODIIUM HYPOCHLORITE SOLN 5 PERCENT --",
                "quantity": "1"
            },
            {
                "id": 67,
                "code": "CHCHBDLAB38",
                "item_name": "TESTT TUBE BRUSH- -",
                "quantity": "1"
            },
            {
                "id": 68,
                "code": "CHCHBDLAB37",
                "item_name": "HB PIIPETTE--",
                "quantity": "1"
            },
            {
                "id": 69,
                "code": "CHCHBDLAB36",
                "item_name": "HB TUUBE--",
                "quantity": "1"
            },
            {
                "id": 70,
                "code": "CHCHBDLAB35",
                "item_name": "BLUE TIIPS--",
                "quantity": "1"
            },
            {
                "id": 71,
                "code": "CHCHBDLAB34",
                "item_name": "YELLOWW TIPS--",
                "quantity": "1"
            },
            {
                "id": 72,
                "code": "CHCHBDLAB33",
                "item_name": "B BILIRUBIN KIT EERBA--",
                "quantity": "1"
            },
            {
                "id": 73,
                "code": "CHCHBDLAB32",
                "item_name": "UREA KKIT ERBA--",
                "quantity": "1"
            },
            {
                "id": 74,
                "code": "CHCHBDLAB31",
                "item_name": "CREATIINE KITT ERBA--",
                "quantity": "1"
            },
            {
                "id": 75,
                "code": "CHCHBDLAB30",
                "item_name": "GLUCOSE REAGENT ERBA--",
                "quantity": "1"
            },
            {
                "id": 76,
                "code": "CHCHBDLAB29",
                "item_name": "TGL KITT EERBA--",
                "quantity": "1"
            },
            {
                "id": 77,
                "code": "CHCHBDLAB28",
                "item_name": "N 10 HCLLL--",
                "quantity": "1"
            },
            {
                "id": 78,
                "code": "CHCHBDLAB27",
                "item_name": "GLASS TEST TUUBES--",
                "quantity": "1"
            },
            {
                "id": 79,
                "code": "CHCHBDLAB26",
                "item_name": "celll counter printer roll ING PRINT--",
                "quantity": "1"
            },
            {
                "id": 80,
                "code": "CHCHBDLAB25",
                "item_name": "Seruum Uriic_Acid ERBA--",
                "quantity": "1"
            },
            {
                "id": 81,
                "code": "CHCHBDLAB24",
                "item_name": "Seerum_ ALBUMIN ERBA--",
                "quantity": "1"
            },
            {
                "id": 82,
                "code": "CHCHBDLAB23",
                "item_name": "Tisssue Rolee --",
                "quantity": "1"
            },
            {
                "id": 83,
                "code": "CHCHBDLAB22",
                "item_name": "HBSAGG-KITT --",
                "quantity": "1"
            },
            {
                "id": 84,
                "code": "CHCHBDLAB21",
                "item_name": "VDRRLL--",
                "quantity": "1"
            },
            {
                "id": 85,
                "code": "CHCHBDLAB20",
                "item_name": "Urine Contaiinar 30ml --",
                "quantity": "1"
            },
            {
                "id": 86,
                "code": "CHCHBDLAB19",
                "item_name": "Wiidaal kit TYDAL --",
                "quantity": "1"
            },
            {
                "id": 87,
                "code": "CHCHBDLAB18",
                "item_name": "CLOT TUBES PLAIN--",
                "quantity": "1"
            },
            {
                "id": 88,
                "code": "CHCHBDLAB17",
                "item_name": "Celll Pack 20 LTR syysmex--",
                "quantity": "1"
            },
            {
                "id": 89,
                "code": "CHCHBDLAB16",
                "item_name": "Stometoolyser WH 500ML syssmex--",
                "quantity": "1"
            },
            {
                "id": 90,
                "code": "CHCHBDLAB15",
                "item_name": "EDTA K3 TUUBES 2ML--",
                "quantity": "1"
            },
            {
                "id": 91,
                "code": "CHCHBDLAB14",
                "item_name": "Denguee Caards--",
                "quantity": "1"
            },
            {
                "id": 92,
                "code": "CHCHBDLAB13",
                "item_name": "UPT Caardss--",
                "quantity": "1"
            },
            {
                "id": 93,
                "code": "CHCHBDLAB12",
                "item_name": "Urine Sugerr Striips 2 PARA--",
                "quantity": "1"
            },
            {
                "id": 94,
                "code": "CHCHBDLAB11",
                "item_name": "Blood Groupe KITT MERISERA--",
                "quantity": "1"
            },
            {
                "id": 95,
                "code": "CHCHBDLAB10",
                "item_name": "blood glucoose Strips-- ONCALL PLUS",
                "quantity": "1"
            },
            {
                "id": 96,
                "code": "CHCHBDLAB09",
                "item_name": "HDLL EERBA--",
                "quantity": "1"
            },
            {
                "id": 97,
                "code": "CHCHBDLAB08",
                "item_name": "Triiglyyceride erba--",
                "quantity": "1"
            },
            {
                "id": 98,
                "code": "CHCHBDLAB07",
                "item_name": "SGOTtt erba--",
                "quantity": "1"
            },
            {
                "id": 99,
                "code": "CHCHBDLAB06",
                "item_name": "Totall Choleestrol KIT ERBA--",
                "quantity": "1"
            },
            {
                "id": 100,
                "code": "CHCHBDLAB05",
                "item_name": "SGPTtt erba--",
                "quantity": "1"
            },
            {
                "id": 101,
                "code": "CHCHBDLAB04",
                "item_name": "Alkaaliine Phosphates erba--",
                "quantity": "1"
            },
            {
                "id": 102,
                "code": "CHCHBDLAB03",
                "item_name": "Total Protoien eerba--",
                "quantity": "1"
            },
            {
                "id": 103,
                "code": "CHCHBDLAB02",
                "item_name": "eeSR PIPPET PACK of 100--",
                "quantity": "1"
            },
            {
                "id": 104,
                "code": "CHCHBDLAB01",
                "item_name": "Seerum Amylase erba S.no\u00a0 Item Code\u00a0 Item Name\u00a0 Scheduled Quantity\u00a0 View Details",
                "quantity": "1"
            }
        ]
    },
    "IND2414": {
        "tender_no": "IND2414",
        "tender_name": "Flexible Bronchoscope",
        "department": "DME Hubli (KMCRI HUBLI)",
        "items": [
            {
                "id": 1,
                "code": "BRONCHO-01",
                "item_name": "Flexible Bronchoscope",
                "quantity": "1"
            }
        ]
    },
    "IND2701": {
        "tender_no": "IND2701",
        "tender_name": "ICU Cots",
        "department": "DME Hubli (KMCRI HUBLI)",
        "items": [
            {
                "id": 1,
                "code": "ICU-COT-01",
                "item_name": "ICU Cots",
                "quantity": "20"
            }
        ]
    }
}

@app.route("/")
def home():
    return "San Tenders 24/7 Cloud Decision Server is Online."

@app.route("/api/register_tender", methods=["POST"])
def register_tender_api():
    data = request.get_json() or {}
    t_no = str(data.get("tender_no") or "").strip().upper()
    if not t_no:
        return jsonify({"status": "error", "message": "Missing tender_no"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO tenders_catalog (tender_no, tender_name, department, items_json)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(tender_no) DO UPDATE SET
        tender_name = excluded.tender_name,
        department = excluded.department,
        items_json = excluded.items_json,
        updated_at = CURRENT_TIMESTAMP
    """, (t_no, data.get("tender_name", ""), data.get("department", ""), json.dumps(data.get("items", []))))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": f"Tender {t_no} registered with {len(data.get('items', []))} items."})

@app.route("/bid")
def bid_page():
    authorized_role = _current_member()
    if not authorized_role:
        return auth_gate_response()

    raw_tender = request.args.get("tender") or request.args.get("id") or "IND2414"
    tender_no = raw_tender.strip().upper()

    # 1. Check URL base64 encoded items parameter
    url_items = []
    d_param = request.args.get("d")
    if d_param:
        try:
            url_items = json.loads(base64.urlsafe_b64decode(d_param.encode()).decode())
        except Exception:
            pass

    # 2. Check DB
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT tender_name, department, items_json FROM tenders_catalog WHERE tender_no = ?", (tender_no,))
    db_row = cur.fetchone()
    
    cur.execute("SELECT name FROM manufacturers ORDER BY name COLLATE NOCASE ASC")
    manufacturers = [r["name"] for r in cur.fetchall()]
    cur.execute("SELECT name FROM approvers ORDER BY id ASC")
    approvers = [r["name"] for r in cur.fetchall()]
    conn.close()
    bulk_manufacturer_options = '<option value="">Choose manufacturer…</option>'
    bulk_manufacturer_options += "".join(
        f'<option value="{html_lib.escape(name, quote=True)}">{html_lib.escape(name)}</option>'
        for name in manufacturers
    )
    bulk_manufacturer_options += '<option value="__ADD__">➕ Add Manufacturer</option>'

    tender = None
    if url_items:
        tender = {
            "tender_no": tender_no,
            "tender_name": request.args.get("name") or f"Tender {tender_no}",
            "department": request.args.get("dept") or "Medical / Health Dept",
            "items": url_items
        }
    elif db_row and db_row["items_json"]:
        tender = {
            "tender_no": tender_no,
            "tender_name": db_row["tender_name"] or f"Tender {tender_no}",
            "department": db_row["department"] or "Medical / Health Dept",
            "items": json.loads(db_row["items_json"])
        }
    elif tender_no in TENDER_CATALOG:
        tender = TENDER_CATALOG[tender_no]
    else:
        # Check base tender
        base_t = tender_no.split('/')[0].split('-')[0].strip()
        if base_t in TENDER_CATALOG:
            tender = TENDER_CATALOG[base_t]

    if not tender or not tender.get("items"):
        tender = {
            "tender_no": tender_no,
            "tender_name": f"Tender {tender_no}",
            "department": "Medical / Health Dept",
            "items": [{"id": 1, "item_name": f"Equipment Scope ({tender_no})", "quantity": 1}]
        }

    approver_opts = "".join([f'<option value="{a}">{a}</option>' for a in approvers])
    items_rows = ""
    for idx, it in enumerate(tender["items"]):
        it_id = it.get("id") or (idx + 1)
        it_name = it.get("item_name") or it.get("name") or f"Item {it_id}"
        it_qty = str(it.get("quantity") or "1")
        it_code = it.get("code")
        code_badge = f'<span style="font-size:11px; background:#e2e8f0; color:#475569; padding:2px 6px; border-radius:4px; margin-right:6px;">{it_code}</span>' if it_code else ''

        it_name_esc = html_lib.escape(str(it_name), quote=True)


        items_rows += f"""
                <tr class="item-row" data-id="{it_id}" data-name="{it_name_esc}" data-qty="{it_qty}" data-manufacturer="" tabindex="0" role="button" aria-label="Assign manufacturer to {it_name_esc}" onclick="assignActiveManufacturer(this)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();assignActiveManufacturer(this)}}">
                    <td class="td-item" style="word-break:break-word; font-size:14px; line-height:1.35;">{code_badge}<b>{it_name_esc}</b></td>
            <td class="td-qty"><span class="qty-badge">{it_qty}</span></td>
            <td class="td-mfg"><span class="manufacturer-display" style="color:#64748b;">Tap to assign</span></td>
        </tr>
        """

    search_box_html = ""
    if len(tender["items"]) > 5:
        search_box_html = '<input type="text" id="filter-input" class="filter-input" onkeyup="filterItems()" placeholder="🔍 Search items by name or code...">'

    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BID APPROVED — {tender['tender_no']}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; padding: 24px 16px; color: #0f172a; line-height: 1.5; -webkit-font-smoothing: antialiased; }}
            .card {{ max-width: 840px; margin: 0 auto; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 30px -5px rgba(15, 23, 42, 0.08), 0 4px 6px -2px rgba(15, 23, 42, 0.03); overflow: hidden; border: 1px solid #e2e8f0; transition: box-shadow 0.2s ease; }}
            .hdr {{ background: linear-gradient(135deg, #15803d 0%, #166534 100%); color: #ffffff; padding: 24px 28px; position: relative; box-shadow: inset 0 1px 0 rgba(255,255,255,0.15); }}
            .badge {{ display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.22); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); color: #ffffff; padding: 4px 12px; border-radius: 9999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; border: 1px solid rgba(255,255,255,0.3); margin-bottom: 8px; text-transform: uppercase; }}
            .hdr h2 {{ font-size: 20px; font-weight: 700; line-height: 1.35; margin: 0 0 6px 0; color: #ffffff; letter-spacing: -0.01em; }}
            .hdr-meta {{ font-size: 13.5px; color: rgba(255, 255, 255, 0.9); font-weight: 500; display: flex; flex-wrap: wrap; gap: 12px; }}
            .approver-bar {{ background: #f8fafc; padding: 12px 28px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; font-size: 13.5px; }}
            .approver-pill {{ display: inline-flex; align-items: center; gap: 6px; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 4px 10px; border-radius: 9999px; color: #15803d; font-weight: 600; font-size: 13px; }}
            .content-pad {{ padding: 20px 28px; }}
            .mfg-panel {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; padding: 12px 16px; background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }}
            .bulk-mfg-select {{ flex: 1; min-width: 170px; padding: 9px 12px; border: 1.5px solid #cbd5e1; border-radius: 8px; font-size: 13.5px; font-weight: 500; background: #ffffff; color: #0f172a; outline: none; transition: all 0.15s ease; cursor: pointer; }}
            .bulk-mfg-select:focus {{ border-color: #22c55e; box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.15); }}
            .filter-input {{ width: 100%; padding: 10px 14px; margin-bottom: 12px; border: 1.5px solid #cbd5e1; border-radius: 8px; font-size: 13.5px; outline: none; transition: all 0.15s ease; }}
            .filter-input:focus {{ border-color: #22c55e; box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.15); }}
            .table-wrap {{ max-height: 520px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.02); }}
            table {{ width: 100%; border-collapse: separate; border-spacing: 0; }}
            th {{ position: sticky; top: 0; z-index: 10; background: #f8fafc; color: #475569; font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 11px 14px; border-bottom: 1px solid #e2e8f0; text-align: left; }}
            td {{ padding: 12px 14px; border-bottom: 1px solid #f1f5f9; font-size: 13.5px; vertical-align: middle; }}
            .item-row {{ cursor: pointer; transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1); outline: none; }}
            .item-row:hover {{ background-color: #f8fafc; }}
            .item-row:focus-visible {{ outline: 2px solid #22c55e; outline-offset: -2px; }}
            .item-row.is-assigned {{ background-color: #f0fdf4; }}
            .td-qty {{ text-align: center; }}
            .qty-badge {{ display: inline-block; padding: 3px 8px; background: #eff6ff; color: #2563eb; font-weight: 700; border-radius: 9999px; font-size: 13px; min-width: 28px; text-align: center; }}
            .manufacturer-display {{ display: inline-flex; align-items: center; justify-content: center; padding: 5px 12px; border-radius: 9999px; background: #f1f5f9; font-size: 12.5px; font-weight: 500; color: #64748b; border: 1px solid #e2e8f0; transition: all 0.15s ease; white-space: nowrap; }}
            .item-row.is-assigned .manufacturer-display {{ color: #15803d !important; background: #dcfce7; font-weight: 700; border-color: #bbf7d0; box-shadow: 0 1px 2px rgba(22, 101, 52, 0.05); }}
            .btn-sub {{ display: block; width: 100%; margin: 18px 0 0 0; background: linear-gradient(135deg, #16a34a 0%, #15803d 100%); color: #ffffff; border: none; padding: 15px 24px; font-size: 15.5px; font-weight: 700; border-radius: 10px; cursor: pointer; text-align: center; box-shadow: 0 4px 12px rgba(22, 163, 74, 0.22); transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1); letter-spacing: 0.01em; }}
            .btn-sub:hover {{ transform: translateY(-1px); box-shadow: 0 6px 18px rgba(22, 163, 74, 0.32); }}
            .btn-sub:active {{ transform: translateY(0); }}
            .modal {{ display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(15, 23, 42, 0.5); backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px); align-items: center; justify-content: center; z-index: 99; }}
            .modal-content {{ background: #ffffff; padding: 24px; border-radius: 16px; width: 90%; max-width: 390px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04); }}
            @media (max-width: 600px) {{
                body {{ padding: 10px 8px; }}
                .card {{ border-radius: 12px; }}
                .hdr {{ padding: 16px 16px; }}
                .hdr h2 {{ font-size: 17px !important; }}
                .approver-bar {{ padding: 10px 16px; font-size: 13px; }}
                .content-pad {{ padding: 14px 12px !important; }}
                th, td {{ padding: 9px 8px; }}
                .th-qty, .td-qty {{ width: 40px !important; }}
                .th-mfg, .td-mfg {{ width: 110px !important; min-width: 100px !important; }}
                .manufacturer-display {{ font-size: 12px !important; padding: 4px 8px !important; }}
                .btn-sub {{ padding: 13px; font-size: 14.5px; }}
            }}
        </style>
    </head>
    <body>
        <div class="card" id="form-card" style="display:none;">
            <div class="hdr">
                <span class="badge">🟢 Bid Approved</span>
                <h2>{tender['tender_name']}</h2>
                <div class="hdr-meta"><span><b>Tender:</b> {tender['tender_no']}</span><span><b>Dept:</b> {tender['department']}</span></div>
            </div>
            <div class="approver-bar">
                <div style="display:flex; align-items:center; gap:8px;"><b>👤 Approver:</b> <span class="approver-pill" id="approver-display">{authorized_role}</span></div>
                <input type="hidden" id="approver-select" value="{authorized_role}">
            </div>
            <div class="content-pad">
                {search_box_html}
                <div class="mfg-panel">
                    <label for="bulk-manufacturer" style="font-weight:600; font-size:13px; color:#334155;">1. Choose manufacturer, then tap its items:</label>
                    <select id="bulk-manufacturer" class="bulk-mfg-select" onchange="handleActiveManufacturerChange(this)">
                        {bulk_manufacturer_options}
                    </select>
                </div>
                <div style="margin-bottom: 10px; display:flex; justify-content:space-between; align-items:center; color:#475569; font-size:13px;">
                    <span>Tap an assigned item again to remove it.</span>
                    <span id="match-count" style="font-size:12px; color:#64748b;"></span>
                </div>
                <div class="table-wrap">
                    <table>
                        <thead style="position: sticky; top: 0; z-index: 10;">
                            <tr><th class="th-item">Item — tap to assign</th><th class="th-qty" style="text-align:center; width:46px;">Qty</th><th class="th-mfg" style="width:115px;">Manufacturer</th></tr>
                        </thead>
                        <tbody id="items-tbody">{items_rows}</tbody>
                    </table>
                </div>
            </div>
            <button type="button" class="btn-sub" id="sub-btn" onclick="submitAllocation()">SUBMIT MANUFACTURER ALLOCATION</button>
        </div>

        <div class="modal" id="add-modal">
            <div class="modal-content">
                <h3 style="margin-top:0;">➕ Add Manufacturer</h3>
                <input type="text" id="new-mfg-input" placeholder="e.g. Olympus, Philips" style="width:100%; padding:10px; border:1px solid #cbd5e1; border-radius:6px; margin-bottom:12px;">
                <div style="display:flex; justify-content:flex-end; gap:8px;">
                    <button onclick="document.getElementById('add-modal').style.display='none'" style="padding:6px 12px; background:#f1f5f9; border:none; border-radius:6px;">Cancel</button>
                    <button onclick="addMfg()" style="padding:6px 14px; background:#16a34a; color:white; border:none; border-radius:6px; font-weight:bold;">ADD</button>
                </div>
            </div>
        </div>

        <script>
            const TENDER_NO = {json.dumps(tender['tender_no'])};
            const TENDER_NAME = {json.dumps(tender['tender_name'])};
            const AUTHORIZED_ROLE = {json.dumps(authorized_role)};
            document.getElementById('form-card').style.display = 'block';

            function updateAssignmentCount() {{
                const assigned = document.querySelectorAll('#items-tbody .item-row[data-manufacturer]:not([data-manufacturer=""])').length;
                const count = document.getElementById('match-count');
                if (count) count.textContent = assigned + ' of {len(tender["items"])} items assigned';
            }}
            function filterItems() {{
                const q = document.getElementById('filter-input').value.toLowerCase().trim();
                let matched = 0;
                document.querySelectorAll('#items-tbody tr').forEach(r => {{
                    const txt = r.innerText.toLowerCase();
                    const show = !q || txt.includes(q);
                    r.style.display = show ? '' : 'none';
                    if (show) matched++;
                }});
                const cnt = document.getElementById('match-count');
                if (cnt) cnt.textContent = q ? (matched + ' matching items') : '';
            }}
            function handleActiveManufacturerChange(select) {{
                if (select.value === '__ADD__') {{
                    document.getElementById('new-mfg-input').value = '';
                    document.getElementById('add-modal').style.display = 'flex';
                }}
            }}
            function assignActiveManufacturer(row) {{
                const manufacturerSelect = document.getElementById('bulk-manufacturer');
                const manufacturer = manufacturerSelect.value;
                if (!manufacturer || manufacturer === '__ADD__') {{
                    alert('Choose a manufacturer first.');
                    manufacturerSelect.focus();
                    return;
                }}
                const current = row.dataset.manufacturer || '';
                const next = current === manufacturer ? '' : manufacturer;
                row.dataset.manufacturer = next;
                const badge = row.querySelector('.manufacturer-display');
                badge.textContent = next || 'Tap to assign';
                row.classList.toggle('is-assigned', Boolean(next));
                row.setAttribute('aria-label', (next ? 'Assigned to ' + next + ': ' : 'Assign manufacturer to ') + row.dataset.name);
                updateAssignmentCount();
            }}
            function addMfg() {{
                const val = document.getElementById('new-mfg-input').value.trim();
                if (!val) return;
                fetch('/api/add_manufacturer', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{name: val}})
                }})
                .then(r => {{
                    if (!r.ok) throw new Error('Server returned HTTP ' + r.status);
                    return r.json();
                }})
                .then(d => {{
                    const select = document.getElementById('bulk-manufacturer');
                    const current = select.value;
                    select.replaceChildren(new Option('Choose manufacturer…', ''));
                    d.manufacturers.forEach(name => select.add(new Option(name, name)));
                    select.add(new Option('➕ Add Manufacturer', '__ADD__'));
                    select.value = d.manufacturers.find(
                        name => name.toLowerCase() === val.toLowerCase()
                    ) || current;
                    document.getElementById('add-modal').style.display = 'none';
                }})
                .catch(error => alert('Could not add manufacturer: ' + error.message));
            }}
            function submitAllocation() {{
                const approver = (document.getElementById('approver-select') && document.getElementById('approver-select').value) ? document.getElementById('approver-select').value : 'Kamal Sir';
                const rows = Array.from(document.querySelectorAll('.item-row'));
                
                const allocs = [];
                rows.forEach(r => {{
                    const mfg = r.dataset.manufacturer || '';
                    if (mfg) {{
                        allocs.push({{
                            item_id: r.getAttribute('data-id') || '1',
                            item_name: r.getAttribute('data-name') || 'Item',
                            quantity: r.getAttribute('data-qty') || '1',
                            manufacturer: mfg
                        }});
                    }}
                }});

                if (allocs.length === 0) {{
                    return alert('Assign a manufacturer to at least one item before submitting.');
                }}

                const subBtn = document.getElementById('sub-btn');
                subBtn.disabled = true;
                subBtn.innerText = 'SAVING ALLOCATION...';
                const sendingWindow = window.open('about:blank', '_blank');
                fetch('/api/submit_allocation', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        tender_no: TENDER_NO,
                        tender_name: TENDER_NAME,
                        approved_by: approver,
                        allocations: allocs
                    }})
                }})
                .then(r => {{
                    if (!r.ok) throw new Error('Server returned HTTP ' + r.status);
                    return r.json();
                }})
                .then(d => {{
                    if (d.status !== 'ok') throw new Error(d.message || 'Error saving');
                    const sendingUrl = '/decision-sending/' + d.action_id;
                    if (sendingWindow) {{
                        sendingWindow.location.href = sendingUrl;
                        document.getElementById('form-card').innerHTML =
                            '<h2>Decision recorded</h2><p>Continue in the sending page that opened.</p>';
                    }} else {{
                        window.location.assign(sendingUrl);
                    }}
                }})
                .catch(err => {{
                    if (sendingWindow) sendingWindow.close();
                    alert('Submission failed: ' + err.message);
                    subBtn.disabled = false;
                    subBtn.innerText = 'SUBMIT MANUFACTURER ALLOCATION';
                }});
            }}
            updateAssignmentCount();
        </script>
    </body>
    </html>
    """
    return html

@app.route("/dontbid")
def dont_bid():
    authorized_role = _current_member()
    if not authorized_role:
        return auth_gate_response()

    raw_tender = request.args.get("tender") or request.args.get("id") or "IND2414"
    tender_no = raw_tender.strip().upper()

    return f"""    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Not Bid — {html_lib.escape(tender_no)}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body style="font-family:Segoe UI, sans-serif; background:#f8fafc; color:#0f172a; text-align:center; padding:32px;">
        <main style="max-width:440px; margin:40px auto; background:white; padding:28px; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,.08);">
            <h1>Record NOT BID decision</h1>
            <p>Tender <b>{html_lib.escape(tender_no)}</b></p>
            <p>Decision by <b>{html_lib.escape(authorized_role)}</b></p>
            <button id="submit-decision" type="button" onclick="submitNotBid()" style="padding:12px 18px; border:0; border-radius:8px; background:#b91c1c; color:white; font-weight:700;">Submit NOT BID</button>
            <p id="decision-status" role="status"></p>
        </main>
        <script>
            const decisionStorageKey = 'san-tender-share:' + {json.dumps(tender_no)};
            const decisionStatus = document.getElementById('decision-status');
            const savedDecision = sessionStorage.getItem(decisionStorageKey);
            if (savedDecision) {{
                try {{
                    const actionId = JSON.parse(savedDecision).action_id;
                    if (actionId) {{
                        window.location.replace('/decision-sending/' + actionId);
                    }}
                }} catch (error) {{
                    sessionStorage.removeItem(decisionStorageKey);
                }}
            }}
            async function submitNotBid() {{
                if (sessionStorage.getItem(decisionStorageKey)) {{
                    const actionId = JSON.parse(sessionStorage.getItem(decisionStorageKey)).action_id;
                    window.location.replace('/decision-sending/' + actionId);
                    return;
                }}
                const button = document.getElementById('submit-decision');
                const sendingWindow = window.open('about:blank', '_blank');
                button.disabled = true;
                button.textContent = 'SAVING DECISION...';
                fetch('/api/record_dontbid', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{tender_no: {json.dumps(tender_no)}}})
                }})
                .then(async response => {{
                    const result = await response.json();
                    if (!response.ok || result.status !== 'ok') {{
                        throw new Error(result.message || 'Decision could not be saved.');
                    }}
                    sessionStorage.setItem(decisionStorageKey, JSON.stringify({{action_id: result.action_id}}));
                    const sendingUrl = '/decision-sending/' + result.action_id;
                    if (sendingWindow) {{
                        sendingWindow.location.href = sendingUrl;
                        document.querySelector('main').innerHTML =
                            '<h1>Decision recorded</h1><p>Continue in the sending page that opened.</p>';
                    }} else {{
                        window.location.replace(sendingUrl);
                    }}
                }})
                .catch(error => {{
                    if (sendingWindow) sendingWindow.close();
                    decisionStatus.textContent = 'Decision was not saved: ' + error.message;
                    decisionStatus.style.color = '#b91c1c';
                    button.disabled = false;
                    button.textContent = 'Submit NOT BID';
                }});
            }}
            if (savedDecision) document.getElementById('submit-decision').disabled = true;
        </script>
    </body>
    </html>
    """

@app.route("/decision-sending/<int:action_id>")
def decision_sending_page(action_id):
    if not _current_member():
        return auth_gate_response()

    try:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT action_type, tender_no, data_json FROM pending_sync WHERE id = ?",
                (action_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return "This decision has already been cleared from Render.", 404
        if row["action_type"] not in {"BID_ALLOCATION", "NOT_BID"}:
            return "This action is not a manager decision.", 404

        action_data = json.loads(row["data_json"])
        whatsapp_text = _whatsapp_decision_message(row["action_type"], action_data)
        whatsapp_url = "https://api.whatsapp.com/send?text=" + urllib.parse.quote(whatsapp_text)
        html = render_template_string(
            """<!doctype html>
            <html lang="en">
            <head>
                <title>Send Tender Decision</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family:Segoe UI,sans-serif; background:#f8fafc; color:#0f172a; padding:20px; text-align:center; }
                    main { max-width:480px; margin:32px auto; background:#fff; padding:28px; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,.08); }
                    pre { white-space:pre-wrap; text-align:left; background:#f1f5f9; padding:14px; border-radius:8px; }
                    button, .send-link { display:inline-block; margin:8px; padding:12px 18px; border:0; border-radius:8px; font-weight:700; text-decoration:none; cursor:pointer; }
                    .send-link { background:#25D366; color:#fff; }
                    button { background:#166534; color:#fff; }
                </style>
            </head>
            <body>
                <main>
                    <h1>Send this decision to the WhatsApp group</h1>
                    <p>Tender {{ tender_no }} is recorded. Choose the correct decision group in WhatsApp and send this prepared message.</p>
                    <pre>{{ message }}</pre>
                    <a class="send-link" href="{{ whatsapp_url }}" target="_blank" rel="noopener noreferrer">Continue to WhatsApp</a>
                    <p>After sending, return here and confirm. The local scanner must also sync this decision before Render deletes it.</p>
                    <button id="sent-button" type="button">Sent to the group</button>
                    <p id="status" role="status"></p>
                </main>
                <script>
                    const actionId = {{ action_id|tojson }};
                    const button = document.getElementById('sent-button');
                    const status = document.getElementById('status');
                    button.addEventListener('click', async () => {
                        button.disabled = true;
                        try {
                            const response = await fetch('/api/mark_whatsapp_shared', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({id: actionId})
                            });
                            const result = await response.json();
                            if (!response.ok || result.status !== 'ok') {
                                throw new Error(result.message || 'Could not confirm the WhatsApp send.');
                            }
                            status.textContent = result.message;
                            status.style.color = '#15803d';
                            window.close();
                            window.setTimeout(() => {
                                status.textContent = 'Confirmation saved. You can close this page.';
                            }, 250);
                        } catch (error) {
                            status.textContent = error.message;
                            status.style.color = '#b91c1c';
                            button.disabled = false;
                        }
                    });
                </script>
            </body>
            </html>""",
            tender_no=row["tender_no"],
            message=whatsapp_text,
            whatsapp_url=whatsapp_url,
            action_id=action_id,
        )
        response = app.make_response(html)
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception as e:
        return f"Could not load the decision sending page: {e}", 500

_FAILED_LOGIN_ATTEMPTS = {}
_LOGIN_LOCK = threading.Lock()

def _is_login_rate_limited(ip_address, max_attempts=5, window_seconds=300):
    now = time.time()
    with _LOGIN_LOCK:
        attempts = [t for t in _FAILED_LOGIN_ATTEMPTS.get(ip_address, []) if now - t < window_seconds]
        _FAILED_LOGIN_ATTEMPTS[ip_address] = attempts
        return len(attempts) >= max_attempts

def _record_failed_login(ip_address):
    now = time.time()
    with _LOGIN_LOCK:
        attempts = _FAILED_LOGIN_ATTEMPTS.setdefault(ip_address, [])
        attempts.append(now)

def _reset_failed_logins(ip_address):
    with _LOGIN_LOCK:
        _FAILED_LOGIN_ATTEMPTS.pop(ip_address, None)

@app.route("/api/auth/login", methods=["POST"])
def login_member():
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
    if _is_login_rate_limited(ip_address):
        return jsonify({
            "status": "error",
            "message": "Too many failed login attempts. Please wait 5 minutes."
        }), 429
    data = request.get_json(silent=True) or {}
    access_code = data.get("access_code")
    codes = _configured_access_codes()
    if codes is None:
        return jsonify({
            "status": "error",
            "message": "Member access codes are not configured on the server."
        }), 503
    if not isinstance(access_code, str) or not 24 <= len(access_code) <= 256:
        _record_failed_login(ip_address)
        return jsonify({"status": "error", "message": "Enter a valid member access code."}), 400

    role = next(
        (member for member, expected in codes.items() if hmac.compare_digest(access_code, expected)),
        None,
    )
    if role is None:
        _record_failed_login(ip_address)
        return jsonify({"status": "error", "message": "Incorrect access code."}), 401

    _reset_failed_logins(ip_address)

    session.clear()
    session["authorized_role"] = role
    session.permanent = True
    return jsonify({"status": "ok", "role": role})


@app.route("/api/auth/status")
def auth_status():
    role = _current_member()
    response = jsonify({"authenticated": role is not None, "role": role})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/record_dontbid", methods=["POST"])
@require_member
def record_dontbid_api():
    data = request.get_json() or {}
    tender_no = (data.get("tender_no") or "").strip().upper()
    user_name = _current_member()
    if tender_no:
        try:
            decision_data = {
                "tender_no": tender_no,
                "action": "NOT_BID",
                "approved_by": user_name,
                "requires_whatsapp_share": True,
                "whatsapp_shared": False,
            }
            whatsapp_text = _whatsapp_decision_message("NOT_BID", decision_data)
            conn = get_db()
            try:
                cur = conn.cursor()
                cur.execute("""
                INSERT INTO pending_sync (action_type, tender_no, data_json, synced)
                VALUES ('NOT_BID', ?, ?, 0)
                """, (tender_no, json.dumps(decision_data)))
                action_id = cur.lastrowid
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return jsonify({
                "status": "ok",
                "action_id": action_id,
                "whatsapp_text": whatsapp_text,
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "error"}), 400

@app.route("/api/add_manufacturer", methods=["POST"])
@require_member
def add_mfg_api():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if name:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO manufacturers (name) VALUES (?)", (name,))
        conn.commit()
        cur.execute("SELECT name FROM manufacturers ORDER BY name COLLATE NOCASE ASC")
        all_mfgs = [r["name"] for r in cur.fetchall()]
        conn.close()
        return jsonify({"status": "ok", "manufacturers": all_mfgs})
    return jsonify({"status": "error", "message": "Name required"}), 400

@app.route("/api/submit_allocation", methods=["POST"])
@require_member
def submit_allocation():
    data = request.get_json() or {}
    tender_no = (data.get("tender_no") or "").strip().upper()
    data["approved_by"] = _current_member()
    data["requires_whatsapp_share"] = True
    data["whatsapp_shared"] = False
    try:
        whatsapp_text = _whatsapp_decision_message("BID_ALLOCATION", data)
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO pending_sync (action_type, tender_no, data_json, synced)
            VALUES ('BID_ALLOCATION', ?, ?, 0)
            """, (tender_no, json.dumps(data)))
            action_id = cur.lastrowid
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return jsonify({
            "status": "ok",
            "message": "Saved to cloud pending sync",
            "action_id": action_id,
            "whatsapp_text": whatsapp_text,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/pending_actions")
def get_pending():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, action_type, tender_no, data_json, created_at FROM pending_sync WHERE synced = 0 ORDER BY id ASC")
    rows = cur.fetchall()
    actions = []
    for r in rows:
        actions.append({
            "id": r["id"],
            "action_type": r["action_type"],
            "tender_no": r["tender_no"],
            "data": json.loads(r["data_json"]),
            "created_at": r["created_at"]
        })
    conn.close()
    return jsonify(actions)

@app.route("/api/mark_synced", methods=["POST"])
def mark_synced():
    data = request.get_json() or {}
    sync_id = data.get("id")
    if isinstance(sync_id, bool) or not isinstance(sync_id, int) or sync_id <= 0:
        return jsonify({"status": "error", "message": "A valid action id is required."}), 400
    try:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT data_json FROM pending_sync WHERE id = ?",
                (sync_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return jsonify({"status": "ok", "message": "Action was already removed."})
            action_data = json.loads(row["data_json"])
            requires_share = action_data.get("requires_whatsapp_share") is True
            shared = action_data.get("whatsapp_shared") is True
            if requires_share and not shared:
                conn.execute("UPDATE pending_sync SET synced = 1 WHERE id = ?", (sync_id,))
                message = "Local sync recorded; waiting for WhatsApp send confirmation."
            else:
                conn.execute("DELETE FROM pending_sync WHERE id = ?", (sync_id,))
                message = "Local sync recorded and action removed."
            conn.commit()
            return jsonify({"status": "ok", "message": message})
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/mark_whatsapp_shared", methods=["POST"])
@require_member
def mark_whatsapp_shared():
    data = request.get_json(silent=True) or {}
    action_id = data.get("id")
    if isinstance(action_id, bool) or not isinstance(action_id, int) or action_id <= 0:
        return jsonify({"status": "error", "message": "A valid action id is required."}), 400

    try:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT data_json, synced FROM pending_sync WHERE id = ?",
                (action_id,),
            ).fetchone()
            if row is None:
                return jsonify({"status": "error", "message": "This response has already been removed."}), 404

            action_data = json.loads(row["data_json"])
            if action_data.get("requires_whatsapp_share") is not True:
                return jsonify({"status": "error", "message": "This response does not require WhatsApp share confirmation."}), 409
            action_data["whatsapp_shared"] = True
            conn.execute(
                "UPDATE pending_sync SET data_json = ? WHERE id = ?",
                (json.dumps(action_data), action_id),
            )
            if row["synced"]:
                conn.execute("DELETE FROM pending_sync WHERE id = ?", (action_id,))
                message = "WhatsApp send confirmed; local sync was already complete, so the response was removed."
            else:
                message = "WhatsApp send confirmed; the response will be removed after the local scanner syncs it."
            conn.commit()
            return jsonify({"status": "ok", "message": message})
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
