import os
import json
import sqlite3
import base64
import urllib.parse
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

INITIAL_APPROVERS = ["Kamal Sir", "Uday Sir", "Developer"]

AUTHORIZED_MEMBERS = {
    "7760969517": "Developer",
    "9845295400": "Kamal Sir",
    "9980304157": "Uday Sir"
}

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

        mfg_opts = '<option value="">Select ▾</option>'
        for m in manufacturers:
            mfg_opts += f'<option value="{m}">{m}</option>'
        mfg_opts += '<option value="__ADD__">➕ Add Manufacturer</option>'

        items_rows += f"""
        <tr class="item-row" data-id="{it_id}" data-name="{it_name}" data-qty="{it_qty}">
            <td class="td-sel" style="text-align:center;"><input type="checkbox" class="item-select" checked onchange="toggleRow(this)" style="width:18px; height:18px; accent-color:#16a34a;"></td>
            <td class="td-item" style="word-break:break-word; font-size:14px; line-height:1.35;">{code_badge}<b>{it_name}</b></td>
            <td class="td-qty" style="text-align:center; font-weight:bold; color:#2563eb; font-size:14px;">{it_qty}</td>
            <td class="td-mfg">
                <select class="mfg-select" onchange="handleMfg(this)" style="width:100%; padding:7px 4px; border-radius:6px; border:1px solid #cbd5e1; font-size:13px; background:white; font-weight:500;">
                    {mfg_opts}
                </select>
            </td>
        </tr>
        """

    search_box_html = ""
    if len(tender["items"]) > 5:
        search_box_html = '<input type="text" id="filter-input" onkeyup="filterItems()" placeholder="🔍 Search items by name or code..." style="width:100%; padding:9px 12px; margin-bottom:12px; border:1px solid #cbd5e1; border-radius:6px; font-size:14px;">'

    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BID APPROVED — {tender['tender_no']}</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; margin: 0; padding: 15px; color: #0f172a; }}
            .card {{ max-width: 820px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); overflow: hidden; border: 1px solid #e2e8f0; }}
            .hdr {{ background: linear-gradient(135deg, #15803d, #166534); color: white; padding: 20px; }}
            .badge {{ display: inline-block; background: #22c55e; color: white; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 700; margin-bottom: 6px; }}
            .approver-bar {{ background: #f1f5f9; padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 10px 8px; border-bottom: 1px solid #f1f5f9; }}
            th {{ background: #f8fafc; color: #64748b; font-size: 13px; text-transform: uppercase; text-align: left; }}
            .btn-sub {{ display: block; width: calc(100% - 40px); margin: 20px auto; background: #16a34a; color: white; border: none; padding: 16px; font-size: 17px; font-weight: 700; border-radius: 8px; cursor: pointer; text-align: center; }}
            @media (max-width: 600px) {{
                body {{ padding: 6px 4px; }}
                .card {{ border-radius: 8px; }}
                .hdr {{ padding: 14px 12px; }}
                .hdr h2 {{ font-size: 17px !important; }}
                .approver-bar {{ padding: 10px 12px; font-size: 13px; }}
                .content-pad {{ padding: 10px 6px !important; }}
                th, td {{ padding: 8px 4px; }}
                .th-sel, .td-sel {{ width: 34px !important; text-align: center; }}
                .th-qty, .td-qty {{ width: 36px !important; text-align: center; }}
                .th-mfg, .td-mfg {{ width: 100px !important; min-width: 95px !important; max-width: 105px !important; padding: 6px 2px !important; }}
                .mfg-select {{ font-size: 12px !important; padding: 6px 2px !important; }}
                .btn-sub {{ width: calc(100% - 16px); margin: 14px auto; padding: 14px; font-size: 15px; }}
            }}
            .modal {{ display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); align-items: center; justify-content: center; z-index: 99; }}
            .modal-content {{ background: white; padding: 20px; border-radius: 10px; width: 90%; max-width: 380px; }}
        </style>
    </head>
    <body>
        <!-- AUTHORIZATION GATE -->
        <div class="card" id="auth-gate" style="display:none; max-width:440px; margin:40px auto; padding:25px; text-align:center;">
            <div style="font-size: 44px; margin-bottom: 10px;">🔐</div>
            <h2 style="margin: 0 0 8px 0; font-size: 20px; color:#0f172a;">Authorized Access Only</h2>
            <p style="color: #64748b; font-size: 14px; margin-bottom: 20px;">Enter your registered 10-digit mobile number to access tender decisions.</p>
            <input type="tel" id="auth-phone-input" placeholder="Enter 10-digit Mobile Number" maxlength="10" style="width: 100%; padding: 12px; font-size: 16px; border: 1px solid #cbd5e1; border-radius: 8px; margin-bottom: 12px; text-align: center; font-weight: bold; letter-spacing: 1px;">
            <div id="auth-error" style="color: #dc2626; font-size: 13px; font-weight: 600; margin-bottom: 12px; display: none;"></div>
            <button type="button" onclick="verifyPhone()" style="width: 100%; background: #16a34a; color: white; border: none; padding: 13px; font-size: 16px; font-weight: 700; border-radius: 8px; cursor: pointer;">Verify & Enter</button>
        </div>

        <div class="card" id="form-card" style="display:none;">
            <div class="hdr">
                <span class="badge">🟢 BID APPROVED</span>
                <h2 style="margin: 0 0 6px 0;">{tender['tender_name']}</h2>
                <div style="font-size: 14px; opacity: 0.9;">Tender: {tender['tender_no']} | Dept: {tender['department']}</div>
            </div>
            <div class="approver-bar">
                <div style="font-size: 14px;"><b>👤 Approver:</b> <span id="approver-display" style="font-weight:700; color:#15803d; margin-left:6px;"></span></div>
                <input type="hidden" id="approver-select" value="Kamal Sir">
            </div>
            <div class="content-pad" style="padding: 15px 20px;">
                {search_box_html}
                <div style="margin-bottom: 10px; display:flex; justify-content:space-between; align-items:center;">
                    <label style="font-weight: 700; cursor: pointer;"><input type="checkbox" id="sel-all" checked onchange="toggleAll(this)"> SELECT ALL ({len(tender['items'])} Items)</label>
                    <span id="match-count" style="font-size:12px; color:#64748b;"></span>
                </div>
                <div style="max-height: 520px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 6px;">
                    <table>
                        <thead style="position: sticky; top: 0; z-index: 10;">
                            <tr><th class="th-sel" style="text-align:center; width:44px;">Select</th><th class="th-item">Item</th><th class="th-qty" style="text-align:center; width:46px;">Qty</th><th class="th-mfg" style="width:115px;">Manufacturer</th></tr>
                        </thead>
                        <tbody id="items-tbody">{items_rows}</tbody>
                    </table>
                </div>
            </div>
            <button type="button" class="btn-sub" id="sub-btn" onclick="submitAllocation()">SUBMIT MANUFACTURER ALLOCATION</button>
        </div>

        <div class="card" id="success-card" style="display:none; text-align:center; padding: 40px 20px;">
            <div style="font-size: 48px; margin-bottom: 10px;">✅</div>
            <h2 style="color: #166534; margin: 0 0 10px 0;">Manufacturer Allocation Saved</h2>
            <p style="color: #475569;">Recorded successfully. When local PC syncs, it updates local files & database.</p>
            <div id="summary-content" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:15px; text-align:left; margin: 20px auto; max-width:500px;"></div>
            <a id="wa-share-btn" href="#" target="_blank" style="display:inline-block; margin-top:10px; background:#25D366; color:white; padding:14px 24px; border-radius:8px; text-decoration:none; font-weight:bold; font-size:16px; box-shadow: 0 2px 8px rgba(37,211,102,0.3);">
                💬 Share Confirmation to WhatsApp Group
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
            const AUTH_MEMBERS = {{
                "7760969517": "Developer",
                "9845295400": "Kamal Sir",
                "9980304157": "Uday Sir"
            }};

            function checkAuth() {{
                let phone = localStorage.getItem("tender_user_phone");
                const urlParams = new URLSearchParams(window.location.search);
                const p = urlParams.get('phone');
                if (p) phone = p.replace(/\\D/g, '').slice(-10);

                if (phone && AUTH_MEMBERS[phone]) {{
                    grantAccess(phone, AUTH_MEMBERS[phone]);
                }} else {{
                    document.getElementById('auth-gate').style.display = 'block';
                    document.getElementById('form-card').style.display = 'none';
                }}
            }}

            function verifyPhone() {{
                const input = document.getElementById('auth-phone-input');
                const err = document.getElementById('auth-error');
                const phone = input.value.replace(/\\D/g, '').slice(-10);

                if (AUTH_MEMBERS[phone]) {{
                    localStorage.setItem("tender_user_phone", phone);
                    grantAccess(phone, AUTH_MEMBERS[phone]);
                }} else {{
                    err.style.display = 'block';
                    err.innerText = '❌ Access Denied: Unauthorized mobile number.';
                }}
            }}

            function grantAccess(phone, name) {{
                document.getElementById('auth-gate').style.display = 'none';
                document.getElementById('form-card').style.display = 'block';
                const hiddenApprover = document.getElementById('approver-select');
                if (hiddenApprover) hiddenApprover.value = name;
                const displayApprover = document.getElementById('approver-display');
                if (displayApprover) displayApprover.innerText = name;
            }}

            checkAuth();

            let targetSelect = null;
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
                if (cnt) cnt.innerText = q ? (matched + ' matching items') : '';
            }}
            function toggleAll(m) {{
                document.querySelectorAll('.item-select').forEach(cb => {{
                    if (cb.closest('tr').style.display !== 'none') {{
                        cb.checked = m.checked;
                        toggleRow(cb);
                    }}
                }});
            }}
            function toggleRow(cb) {{
                const row = cb.closest('tr');
                row.querySelector('.mfg-select').disabled = !cb.checked;
                row.style.opacity = cb.checked ? '1' : '0.4';
            }}
            function handleMfg(s) {{
                if (s.value === '__ADD__') {{
                    targetSelect = s;
                    document.getElementById('new-mfg-input').value = '';
                    document.getElementById('add-modal').style.display = 'flex';
                    return;
                }}
                const chosen = s.value;
                if (!chosen) return;
                const row = s.closest('tr');
                if (row) {{
                    const cb = row.querySelector('.item-select');
                    if (cb && !cb.checked) {{
                        cb.checked = true;
                        toggleRow(cb);
                    }}
                }}
                document.querySelectorAll('#items-tbody tr').forEach(r => {{
                    const cb = r.querySelector('.item-select');
                    if (cb && cb.checked) {{
                        const sel = r.querySelector('.mfg-select');
                        if (sel && sel !== s) {{
                            sel.value = chosen;
                        }}
                    }}
                }});
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
                        let h = '<option value="">Select ▾</option>';
                        d.manufacturers.forEach(m => {{
                            h += `<option value="${{m}}" ${{m.toLowerCase() === cur.toLowerCase() ? 'selected' : ''}}>${{m}}</option>`;
                        }});
                        h += '<option value="__ADD__">➕ Add Manufacturer</option>';
                        sel.innerHTML = h;
                    }});
                    if (val) {{
                        document.querySelectorAll('#items-tbody tr').forEach(r => {{
                            const cb = r.querySelector('.item-select');
                            if (cb && cb.checked) {{
                                const sel = r.querySelector('.mfg-select');
                                if (sel) sel.value = val;
                            }}
                        }});
                    }}
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
                        list += `<li><b>${{a.item_name}}</b> (Qty: ${{a.quantity}}) ➔ <span style="color:#16a34a; font-weight:bold;">${{a.manufacturer}}</span></li>`;
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
                    const waUrl = 'https://api.whatsapp.com/send?text=' + encodeURIComponent(waText);
                    document.getElementById('wa-share-btn').href = waUrl;
                    document.getElementById('success-card').style.display = 'block';
                    setTimeout(function() {{
                        window.location.href = waUrl;
                    }}, 700);
                }});
            }}
        </script>
    </body>
    </html>
    """
    return html

@app.route("/dontbid")
def dont_bid():
    raw_tender = request.args.get("tender") or request.args.get("id") or "IND2414"
    tender_no = raw_tender.strip().upper()

    return f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Tender Decision — {tender_no}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; padding: 20px; color: #0f172a; text-align: center; }}
            .card {{ max-width: 440px; margin: 40px auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; }}
        </style>
    </head>
    <body>
        <div class="card" id="auth-gate" style="display:none;">
            <div style="font-size: 40px; margin-bottom: 10px;">🔐</div>
            <h2 style="margin: 0 0 8px 0; font-size: 20px;">Authorized Access Only</h2>
            <p style="color: #64748b; font-size: 14px; margin-bottom: 20px;">Enter your registered 10-digit mobile number to record decision:</p>
            <input type="tel" id="phone-input" placeholder="10-digit Mobile Number" maxlength="10" style="width: 100%; padding: 12px; font-size: 16px; border: 1px solid #cbd5e1; border-radius: 8px; margin-bottom: 12px; text-align: center; font-weight: bold; letter-spacing: 1px;">
            <div id="auth-error" style="color: #dc2626; font-size: 13px; font-weight: 600; margin-bottom: 12px; display: none;"></div>
            <button type="button" onclick="verifyPhone()" style="width: 100%; background: #dc2626; color: white; border: none; padding: 12px; font-size: 16px; font-weight: 700; border-radius: 8px; cursor: pointer;">Confirm Rejection</button>
        </div>

        <div class="card" id="reject-card" style="display:none; background: #fff5f5; border-color: #fecaca;">
            <h1 style="color: #dc2626; margin: 0 0 10px 0; font-size: 24px;">🚫 MOVED TO NOT DONE</h1>
            <p style="font-size: 16px;">Tender <b>{tender_no}</b> recorded as NOT BID.</p>
            <p style="color: #64748b; font-size: 14px;">Decision by: <b id="user-display" style="color:#0f172a;"></b></p>
            <p style="color: #16a34a; font-weight: 600; font-size: 14px;">Redirecting to WhatsApp...</p>
            <a id="wa-btn" href="#" target="_blank" style="display:inline-block; margin-top:15px; background:#25D366; color:white; padding:12px 20px; border-radius:8px; text-decoration:none; font-weight:bold; font-size:15px;">
                💬 Share to WhatsApp Group
            </a>
        </div>

        <script>
            const AUTH_MEMBERS = {{
                "7760969517": "Developer",
                "9845295400": "Kamal Sir",
                "9980304157": "Uday Sir"
            }};

            function checkAuth() {{
                let phone = localStorage.getItem("tender_user_phone");
                const urlParams = new URLSearchParams(window.location.search);
                const p = urlParams.get('phone');
                if (p) phone = p.replace(/\\D/g, '').slice(-10);

                if (phone && AUTH_MEMBERS[phone]) {{
                    recordRejection(AUTH_MEMBERS[phone]);
                }} else {{
                    document.getElementById('auth-gate').style.display = 'block';
                }}
            }}

            function verifyPhone() {{
                const input = document.getElementById('phone-input');
                const err = document.getElementById('auth-error');
                const phone = input.value.replace(/\\D/g, '').slice(-10);

                if (AUTH_MEMBERS[phone]) {{
                    localStorage.setItem("tender_user_phone", phone);
                    document.getElementById('auth-gate').style.display = 'none';
                    recordRejection(AUTH_MEMBERS[phone]);
                }} else {{
                    err.style.display = 'block';
                    err.innerText = '❌ Access Denied: Unauthorized number.';
                }}
            }}

            function recordRejection(userName) {{
                document.getElementById('auth-gate').style.display = 'none';
                document.getElementById('reject-card').style.display = 'block';
                document.getElementById('user-display').innerText = userName;

                fetch('/api/record_dontbid', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        tender_no: '{tender_no}',
                        approved_by: userName
                    }})
                }});

                const waText = `🚫 *TENDER DECISION — NOT BID*\n\n` +
                               `📌 *Tender:* {tender_no}\n` +
                               `🏢 *Status:* Rejected / Moved to Not Done\n` +
                               `👤 *Decision By:* ${{userName}}\n\n` +
                               `_Recorded in system._`;
                const waUrl = 'https://api.whatsapp.com/send?text=' + encodeURIComponent(waText);
                document.getElementById('wa-btn').href = waUrl;
                setTimeout(function() {{
                    window.location.href = waUrl;
                }}, 700);
            }}

            checkAuth();
        </script>
    </body>
    </html>
    """

@app.route("/api/record_dontbid", methods=["POST"])
def record_dontbid_api():
    data = request.get_json() or {}
    tender_no = (data.get("tender_no") or "").strip().upper()
    user_name = (data.get("approved_by") or "Kamal Sir").strip()
    if tender_no:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO pending_sync (action_type, tender_no, data_json, synced)
        VALUES ('NOT_BID', ?, ?, 0)
        """, (tender_no, json.dumps({"tender_no": tender_no, "action": "NOT_BID", "approved_by": user_name})))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

@app.route("/api/add_manufacturer", methods=["POST"])
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
def submit_allocation():
    data = request.get_json() or {}
    tender_no = data.get("tender_no", "")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO pending_sync (action_type, tender_no, data_json, synced)
    VALUES ('BID_ALLOCATION', ?, ?, 0)
    """, (tender_no, json.dumps(data)))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": "Saved to cloud pending sync"})

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
    if sync_id:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM pending_sync WHERE id = ?", (sync_id,))
        cur.execute("VACUUM")
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "message": f"Action {sync_id} permanently deleted. Zero storage used."})
    return jsonify({"status": "error"}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
