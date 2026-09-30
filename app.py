import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "cloud_tenders.db")

INITIAL_MANUFACTURERS = [
    "GMPL", "Adonis", "Advantage", "Sysmed", "Appasamy", "Shalya",
    "Mindray", "Sonastar", "Karlkaps", "Mediland", "Medimeas",
    "Smith & Nephew", "Times Surgical", "Timelight", "Bell Surgical",
    "Bistos", "Panacea", "CKK", "Santosh Surgical", "Mr ENGG",
    "IFB", "Cnergy", "Clarity", "Radical", "Pridex", "Swemed", "Anand Agencies"
]

INITIAL_APPROVERS = ["Kamal Sir", "Uday Sir"]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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
    CREATE TABLE IF NOT EXISTS pending_sync (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type TEXT, -- 'BID_ALLOCATION' or 'NOT_BID'
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

init_db()

TENDER_CATALOG = {
    "IND2414": {
        "tender_no": "IND2414",
        "tender_name": "Flexible Bronchoscope",
        "department": "DME Hubli (KMCRI HUBLI)",
        "items": [{"id": 1, "item_name": "Flexible Bronchoscope", "quantity": 1}]
    },
    "IND2701": {
        "tender_no": "IND2701",
        "tender_name": "ICU Cots",
        "department": "DME Hubli (KMCRI HUBLI)",
        "items": [{"id": 1, "item_name": "ICU Cots", "quantity": 20}]
    }
}

@app.route("/")
def home():
    return "San Tenders 24/7 Cloud Decision Server is Online."

@app.route("/bid")
def bid_page():
    tender_no = request.args.get("tender") or request.args.get("id") or "IND2414"
    tender = TENDER_CATALOG.get(tender_no)
    if not tender:
        tender = {
            "tender_no": tender_no,
            "tender_name": f"Tender {tender_no}",
            "department": "Medical / Health Dept",
            "items": [{"id": 1, "item_name": f"Equipment Scope ({tender_no})", "quantity": 1}]
        }

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM manufacturers ORDER BY name COLLATE NOCASE ASC")
    manufacturers = [r["name"] for r in cur.fetchall()]
    cur.execute("SELECT name FROM approvers ORDER BY id ASC")
    approvers = [r["name"] for r in cur.fetchall()]
    conn.close()

    approver_opts = "".join([f'<option value="{a}">{a}</option>' for a in approvers])
    items_rows = ""
    for it in tender["items"]:
        mfg_opts = '<option value="">Select Manufacturer ▼</option>'
        for m in manufacturers:
            mfg_opts += f'<option value="{m}">{m}</option>'
        mfg_opts += '<option value="__ADD__">➕ Add Manufacturer</option>'

        items_rows += f"""
        <tr class="item-row" data-id="{it['id']}" data-name="{it['item_name']}" data-qty="{it['quantity']}">
            <td style="text-align:center;"><input type="checkbox" class="item-select" checked onchange="toggleRow(this)"></td>
            <td><b>{it['item_name']}</b></td>
            <td style="text-align:center; font-weight:bold; color:#2563eb;">{it['quantity']}</td>
            <td>
                <select class="mfg-select" onchange="handleMfg(this)" style="width:100%; padding:8px; border-radius:6px; border:1px solid #cbd5e1;">
                    {mfg_opts}
                </select>
            </td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BID APPROVED — {tender['tender_no']}</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; margin: 0; padding: 15px; color: #0f172a; }}
            .card {{ max-width: 760px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); overflow: hidden; border: 1px solid #e2e8f0; }}
            .hdr {{ background: linear-gradient(135deg, #15803d, #166534); color: white; padding: 20px; }}
            .badge {{ display: inline-block; background: #22c55e; color: white; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 700; margin-bottom: 6px; }}
            .approver-bar {{ background: #f1f5f9; padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; border-bottom: 1px solid #f1f5f9; }}
            th {{ background: #f8fafc; color: #64748b; font-size: 13px; text-transform: uppercase; text-align: left; }}
            .btn-sub {{ display: block; width: calc(100% - 40px); margin: 20px auto; background: #16a34a; color: white; border: none; padding: 16px; font-size: 17px; font-weight: 700; border-radius: 8px; cursor: pointer; text-align: center; }}
            .modal {{ display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); align-items: center; justify-content: center; z-index: 99; }}
            .modal-content {{ background: white; padding: 20px; border-radius: 10px; width: 90%; max-width: 380px; }}
        </style>
    </head>
    <body>
        <div class="card" id="form-card">
            <div class="hdr">
                <span class="badge">🟢 BID APPROVED</span>
                <h2 style="margin: 0 0 6px 0;">{tender['tender_name']}</h2>
                <div style="font-size: 14px; opacity: 0.9;">Tender: {tender['tender_no']} | Dept: {tender['department']}</div>
            </div>
            <div class="approver-bar">
                <b>👤 Approver:</b>
                <select id="approver-select" style="padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e1; font-weight: 600;">
                    {approver_opts}
                </select>
            </div>
            <div style="padding: 15px 20px;">
                <div style="margin-bottom: 10px;">
                    <label style="font-weight: 700; cursor: pointer;"><input type="checkbox" id="sel-all" checked onchange="toggleAll(this)"> SELECT ALL</label>
                </div>
                <table>
                    <thead><tr><th style="text-align:center;">Select</th><th>Item</th><th style="text-align:center;">Qty</th><th>Manufacturer</th></tr></thead>
                    <tbody>{items_rows}</tbody>
                </table>
            </div>
            <button type="button" class="btn-sub" id="sub-btn" onclick="submitAllocation()">SUBMIT MANUFACTURER ALLOCATION</button>
        </div>

        <div class="card" id="success-card" style="display:none; text-align:center; padding: 40px 20px;">
            <div style="font-size: 48px; margin-bottom: 10px;">✅</div>
            <h2 style="color: #166534; margin: 0 0 10px 0;">Manufacturer Allocation Saved</h2>
            <p style="color: #475569;">Recorded successfully. When local PC syncs, it updates local files & database.</p>
            <div id="summary-content" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:15px; text-align:left; margin: 20px auto; max-width:500px;"></div>
            <a id="wa-share-btn" href="#" target="_blank" style="display:inline-block; margin-top:10px; background:#25D366; color:white; padding:14px 24px; border-radius:8px; text-decoration:none; font-weight:bold; font-size:16px; box-shadow: 0 2px 8px rgba(37,211,102,0.3);">
                📲 Share Confirmation to WhatsApp Group
            </a>
            <div style="margin-top:15px; font-size:13px; color:#16a34a; font-weight:600;">Status: Submitted & Persisted 24/7</div>
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
            let targetSelect = null;
            function toggleAll(m) {{
                document.querySelectorAll('.item-select').forEach(cb => {{ cb.checked = m.checked; toggleRow(cb); }});
            }}
            function toggleRow(cb) {{
                const row = cb.closest('tr');
                row.querySelector('.mfg-select').disabled = !cb.checked;
                row.style.opacity = cb.checked ? '1' : '0.5';
            }}
            function handleMfg(s) {{
                if (s.value === '__ADD__') {{
                    targetSelect = s;
                    document.getElementById('new-mfg-input').value = '';
                    document.getElementById('add-modal').style.display = 'flex';
                }}
            }}
            function addMfg() {{
                const val = document.getElementById('new-mfg-input').value.trim();
                if (!val) return;
                fetch('/api/add_manufacturer', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{name: val}})
                }})
                .then(r => r.json())
                .then(d => {{
                    document.querySelectorAll('.mfg-select').forEach(sel => {{
                        let cur = (sel === targetSelect) ? val : sel.value;
                        let h = '<option value="">Select Manufacturer ▼</option>';
                        d.manufacturers.forEach(m => {{
                            h += `<option value="${{m}}" ${{m.toLowerCase() === cur.toLowerCase() ? 'selected' : ''}}>${{m}}</option>`;
                        }});
                        h += '<option value="__ADD__">➕ Add Manufacturer</option>';
                        sel.innerHTML = h;
                    }});
                    document.getElementById('add-modal').style.display = 'none';
                }});
            }}
            function submitAllocation() {{
                const approver = document.getElementById('approver-select').value;
                const allocs = [];
                let err = false;
                document.querySelectorAll('.item-row').forEach(r => {{
                    const cb = r.querySelector('.item-select');
                    if (cb.checked) {{
                        const mfg = r.querySelector('.mfg-select').value;
                        if (!mfg || mfg === '__ADD__') err = true;
                        else allocs.push({{
                            item_id: r.getAttribute('data-id'),
                            item_name: r.getAttribute('data-name'),
                            quantity: r.getAttribute('data-qty'),
                            manufacturer: mfg
                        }});
                    }}
                }});
                if (err) return alert('Please choose a valid manufacturer for all selected items.');
                if (allocs.length === 0) return alert('Please select at least one item.');

                document.getElementById('sub-btn').disabled = true;
                fetch('/api/submit_allocation', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        tender_no: '{tender['tender_no']}',
                        tender_name: '{tender['tender_name']}',
                        approved_by: approver,
                        allocations: allocs
                    }})
                }})
                .then(r => r.json())
                .then(d => {{
                    document.getElementById('form-card').style.display = 'none';
                    let list = '<ul style="margin:6px 0; padding-left:18px;">';
                    let waList = '';
                    allocs.forEach(a => {{ 
                        list += `<li><b>${{a.item_name}}</b> (Qty: ${{a.quantity}}) → <span style="color:#16a34a; font-weight:bold;">${{a.manufacturer}}</span></li>`;
                        waList += `• *${{a.item_name}}* (Qty: ${{a.quantity}}) ➔ *${{a.manufacturer}}*\n`;
                    }});
                    list += '</ul>';
                    document.getElementById('summary-content').innerHTML = `
                        <div><b>Tender:</b> {tender['tender_no']} — {tender['tender_name']}</div>
                        <div><b>Approved By:</b> ${{approver}}</div>
                        <div><b>Items Allocated:</b> ${{list}}</div>
                    `;
                    let waText = `*BID APPROVED & MANUFACTURER ALLOCATED*\n\n` +
                                 `*Tender:* {tender['tender_no']} — {tender['tender_name']}\n` +
                                 `*Approved By:* ${{approver}}\n\n` +
                                 `*Allocated Items:*\n` + waList +
                                 `\n_Recorded in system._`;
                    document.getElementById('wa-share-btn').href = 'https://api.whatsapp.com/send?text=' + encodeURIComponent(waText);
                    document.getElementById('success-card').style.display = 'block';
                }});
            }}
        </script>
    </body>
    </html>
    """
    return html

@app.route("/dontbid")
def dont_bid():
    tender_no = request.args.get("tender") or request.args.get("id") or "IND2414"
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO pending_sync (action_type, tender_no, data_json, synced)
    VALUES ('NOT_BID', ?, ?, 0)
    """, (tender_no, json.dumps({"tender_no": tender_no, "action": "NOT_BID"})))
    conn.commit()
    conn.close()

    wa_text = f"*TENDER DECISION — NOT BID*\\n\\n*Tender:* {tender_no}\\n*Status:* Rejected / Moved to Not Done\\n\\n_Recorded in system._"
    import urllib.parse
    wa_url = "https://api.whatsapp.com/send?text=" + urllib.parse.quote(wa_text)

    return f"""<!DOCTYPE html>
    <html>
    <head><title>Tender Rejected</title><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="font-family: sans-serif; text-align: center; padding: 40px; background: #fff5f5;">
        <h1 style="color: #dc2626;">🔴 MOVED TO NOT DONE</h1>
        <p>Tender <b>{tender_no}</b> recorded as NOT BID.</p>
        <p style="color: #64748b;">Recorded in cloud queue. When local PC syncs, it updates local files automatically.</p>
        <a href="{wa_url}" target="_blank" style="display:inline-block; margin-top:15px; background:#25D366; color:white; padding:12px 24px; border-radius:8px; text-decoration:none; font-weight:bold; font-size:16px;">
            📲 Share Update to WhatsApp Group
        </a>
    </body>
    </html>"""

@app.route("/api/add_manufacturer", methods=["POST"])
def add_mfg_api():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    conn = get_db()
    cur = conn.cursor()
    if name:
        try:
            cur.execute("INSERT INTO manufacturers (name) VALUES (?)", (name,))
            conn.commit()
        except:
            pass
    cur.execute("SELECT name FROM manufacturers ORDER BY name COLLATE NOCASE ASC")
    mfgs = [r["name"] for r in cur.fetchall()]
    conn.close()
    return jsonify({"success": True, "manufacturers": mfgs})

@app.route("/api/submit_allocation", methods=["POST"])
def submit_allocation():
    data = request.get_json() or {}
    tender_no = data.get("tender_no")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO pending_sync (action_type, tender_no, data_json, synced)
    VALUES ('BID_ALLOCATION', ?, ?, 0)
    """, (tender_no, json.dumps(data)))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Saved to cloud queue."})

# Endpoints for Local PC to Sync
@app.route("/api/pending_actions")
def get_pending():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM pending_sync WHERE synced = 0 ORDER BY id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/mark_synced", methods=["POST"])
def mark_synced():
    data = request.get_json() or {}
    sync_id = data.get("id")
    conn = get_db()
    cur = conn.cursor()
    # Delete immediately to ensure zero storage buildup on Render
    cur.execute("DELETE FROM pending_sync WHERE id = ?", (sync_id,))
    # Auto-prune any orphan records older than 1 day
    cur.execute("DELETE FROM pending_sync WHERE created_at < datetime('now', '-1 day')")
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Deleted from cloud buffer."})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
