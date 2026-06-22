"""
RiskCore Phase 2 — Stable Release
All bugs fixed + UX improvements:
- Add Risk now saves correctly and auto-navigates to register
- Dashboard refreshes after every insert
- Status bar with DB health and total risk count
- Refresh buttons on Dashboard and Register
- Last-refreshed timestamp
- Auto-refresh after risk creation / deletion / AI approve
- Better success/error toasts that auto-clear
- Search/filter state preserved on refresh
- Audit log CREATE entries verified
- All None-guard fixes retained from previous pass
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from tkinter import messagebox, filedialog
import sqlite3, json, csv, base64, tempfile, datetime, re, threading, shutil
from pathlib import Path
from collections import defaultdict

# ── Icon ──────────────────────────────────────────────────────────────────────
ICON_B64 = (
    "AAABAAEAEBAAAAAAIADjAAAAFgAAAIlQTkcNChoKAAAADUlIRFIAAAAQAAAAEAgGAAAAH/P/YQAAAKpJ"
    "REFUeJxjZIACXkHx/wwkgs/vXzIykqsZBhiRNZ8X5Sdao+HrjwwMDAwMLMiaYYLIgJA4C7ogOjD+"
    "yILXZSzoAsYfUYVeRrkzMDAwMIgv2wkXO8v/B85mwmk0kQDDBcjgLP8fhidbt0LZmK4jygXYNJFk"
    "ALL/iTIApgFdI8wl6OIo7oPFN3q0GX9kgWtEV4PVC8gJB5tmvF5AN4RfSBCnZgYGKuQFinMjAMZd"
    "RUSuTNrYAAAAAElFTkSuQmCC"
)

def set_icon(w):
    try:
        d = base64.b64decode(ICON_B64)
        t = tempfile.NamedTemporaryFile(delete=False, suffix='.ico')
        t.write(d); t.close()
        w.iconbitmap(t.name)
    except Exception:
        pass

# ── Constants ─────────────────────────────────────────────────────────────────
CATEGORIES     = ["Technical","Operational","Compliance","Strategic",
                  "Financial","Physical","Third Party"]
RISK_STATUS    = ["Open","In Progress","Mitigated","Accepted","Closed"]
NIST_FUNCTIONS = ["Govern","Identify","Protect","Detect","Respond","Recover"]
NIST_CATEGORIES = {
    "Govern":   ["Organizational Context","Risk Management Strategy",
                 "Roles & Responsibilities","Policy","Oversight",
                 "Cybersecurity Supply Chain Risk"],
    "Identify": ["Asset Management","Risk Assessment",
                 "Improvement"],
    "Protect":  ["Identity Management & Access Control","Awareness & Training",
                 "Data Security","Platform Security","Technology Infrastructure Resilience"],
    "Detect":   ["Continuous Monitoring","Adverse Event Analysis"],
    "Respond":  ["Incident Management","Incident Analysis",
                 "Incident Response Reporting","Mitigation","Improvements"],
    "Recover":  ["Incident Recovery Plan Execution","Incident Recovery Communication"],
}
ISO_DOMAINS = [
    "A.5 Organisational Controls",
    "A.6 People Controls",
    "A.7 Physical Controls",
    "A.8 Technological Controls",
]
CIA_COMPONENTS = ["Confidentiality","Integrity","Availability","All Three"]
MITRE_TACTICS  = [
    "Reconnaissance","Resource Development","Initial Access","Execution",
    "Persistence","Privilege Escalation","Defense Evasion","Credential Access",
    "Discovery","Lateral Movement","Collection","Command & Control",
    "Exfiltration","Impact","Not Applicable",
]
CIS_CONTROLS   = [f"CIS-{i}" for i in range(1, 19)] + ["Not Applicable"]
LIKELIHOOD_LBL = {1:"Rare",2:"Unlikely",3:"Possible",4:"Likely",5:"Almost Certain"}
IMPACT_LBL     = {1:"Negligible",2:"Minor",3:"Moderate",4:"Major",5:"Critical"}

# BASE_DIR must point to the folder containing the EXE (or script), not to
# PyInstaller's temporary extraction folder. When PyInstaller builds a
# --onefile bundle, it unpacks everything to a temp dir (e.g.
# C:\Users\...\AppData\Local\Temp\_MEIxxxxxx) at runtime and sets
# __file__ to a path inside that temp dir. That folder is deleted when
# the process exits, which is why riskcore.db, settings.json,
# riskcore_apikey.txt, and riskcore.key all disappeared on restart.
# sys.executable always points to the real EXE regardless of how
# PyInstaller extracted it, so we derive BASE_DIR from there when frozen.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

DB_PATH       = BASE_DIR / "riskcore.db"
API_KEY_FILE  = BASE_DIR / "riskcore_apikey.txt"
SETTINGS_FILE = BASE_DIR / "settings.json"

# ── Theme ─────────────────────────────────────────────────────────────────────
DARK_BG    = "#0D1117"
CARD_BG    = "#161B22"
BORDER     = "#21262D"
ACCENT     = "#DC2626"
ACCENT2    = "#1D4ED8"
TEXT_MAIN  = "#E6EDF3"
TEXT_MUTED = "#7D8590"
GREEN      = "#16A34A"
GOLD       = "#CA8A04"
ORANGE     = "#EA580C"
RED        = "#DC2626"
PURPLE     = "#7C3AED"

# ── Score helpers ─────────────────────────────────────────────────────────────
def score_color(s):
    try: s = int(s or 0)
    except: s = 0
    if s <= 4:  return GREEN
    if s <= 9:  return GOLD
    if s <= 14: return ORANGE
    return RED

def score_label(s):
    try: s = int(s or 0)
    except: s = 0
    if s <= 4:  return "LOW"
    if s <= 9:  return "MEDIUM"
    if s <= 14: return "HIGH"
    return "CRITICAL"

# ── Misc helpers ──────────────────────────────────────────────────────────────
def today():
    return datetime.date.today().isoformat()

def now_str():
    return datetime.datetime.now().strftime("%H:%M:%S")

def sanitise(text, max_len=500):
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    text = text.strip()[:max_len]
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text

def validate_date(s):
    try: datetime.date.fromisoformat(s); return True
    except: return False

def _get_or_create_fernet():
    """
    Returns a cryptography.fernet.Fernet instance backed by a local key
    file. The key file (riskcore.key) lives alongside the database and
    is generated on first use. This protects the Anthropic API key from
    casual disclosure (e.g. opening riskcore_apikey.txt in Notepad,
    accidentally screen-sharing the folder, or syncing it to cloud
    storage in plaintext) without requiring any external secret manager
    — appropriate for a single-user desktop v1.0 app. It is NOT a
    defense against an attacker with full filesystem access to the
    machine (the key file sits next to the encrypted value, as is
    standard for local-only secret-at-rest protection without OS
    keychain integration).
    """
    from cryptography.fernet import Fernet
    key_file = BASE_DIR / "riskcore.key"
    if key_file.exists():
        key = key_file.read_bytes()
    else:
        key = Fernet.generate_key()
        key_file.write_bytes(key)
    return Fernet(key)

def load_api_key():
    """Load and decrypt the stored API key. Transparently migrates a
    legacy plaintext riskcore_apikey.txt (from pre-encryption versions)
    by re-encrypting it on first read, then removing the plaintext file."""
    try:
        from cryptography.fernet import InvalidToken
        f = _get_or_create_fernet()
        if API_KEY_FILE.exists():
            raw = API_KEY_FILE.read_bytes()
            try:
                return f.decrypt(raw).decode().strip()
            except InvalidToken:
                # Not encrypted yet — legacy plaintext file from an
                # older version. Migrate it to encrypted storage.
                plain = raw.decode(errors="ignore").strip()
                if plain.startswith("sk-ant"):
                    save_api_key(plain)
                    return plain
                return ""
    except Exception as e:
        print(f"[api key load error] {e}")
    return ""

def save_api_key(key):
    """Encrypt and persist the API key. Overwrites any previous file."""
    try:
        f = _get_or_create_fernet()
        token = f.encrypt(key.strip().encode())
        API_KEY_FILE.write_bytes(token)
    except Exception as e:
        print(f"[api key save error] {e}")

DEFAULT_SETTINGS = {
    "organisation_name": "Your Organisation",
    "default_classification": "CONFIDENTIAL",
    "last_saved": "",
}

def load_settings():
    """Load persisted app settings (organisation name, default
    classification). Plain JSON — nothing sensitive lives here (the API
    key has its own encrypted file). Falls back to defaults if the file
    is missing or unreadable, so a corrupt/missing settings.json can
    never prevent the app from starting."""
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            merged = dict(DEFAULT_SETTINGS)
            merged.update({k: v for k, v in data.items()
                          if k in DEFAULT_SETTINGS})
            return merged
    except Exception as e:
        print(f"[settings load error] {e}")
    return dict(DEFAULT_SETTINGS)

def save_settings(settings: dict):
    """Persist app settings to settings.json."""
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
        return True
    except Exception as e:
        print(f"[settings save error] {e}")
        return False

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS risks (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            title            TEXT NOT NULL,
            description      TEXT,
            category         TEXT,
            nist_function    TEXT,
            nist_category    TEXT,
            iso_domain       TEXT,
            cia_component    TEXT,
            mitre_tactic     TEXT,
            cis_control      TEXT,
            likelihood       INTEGER CHECK(likelihood BETWEEN 1 AND 5),
            impact           INTEGER CHECK(impact BETWEEN 1 AND 5),
            risk_score       INTEGER DEFAULT 0,
            owner            TEXT,
            status           TEXT DEFAULT 'Open',
            mitigation       TEXT,
            review_date      TEXT,
            date_identified  TEXT,
            date_modified    TEXT,
            source           TEXT DEFAULT 'Manual',
            notes            TEXT,
            ai_suggestion    TEXT,
            pdf_source       TEXT,
            mitre_technique  TEXT,
            inherent_score   INTEGER DEFAULT 0,
            residual_score   INTEGER DEFAULT 0,
            risk_velocity    INTEGER DEFAULT 2,
            confidence       TEXT,
            iso_control      TEXT,
            nist_subcategory TEXT,
            owner_suggestion TEXT,
            existing_controls TEXT,
            priority         TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action    TEXT NOT NULL,
            risk_id   INTEGER,
            detail    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_risks_status ON risks(status);
        CREATE INDEX IF NOT EXISTS idx_risks_score  ON risks(risk_score);
        CREATE INDEX IF NOT EXISTS idx_risks_nist   ON risks(nist_function);
        """)
    _migrate_schema()

# ── Schema migration ──────────────────────────────────────────────────────────
# Single source of truth for every non-id column on `risks`. Used by the
# migration step below to detect and add anything missing from databases
# created by older versions of RiskCore (e.g. the original 24-column
# Phase 1 schema, which predates inherent_score, residual_score,
# risk_velocity, confidence, iso_control, nist_subcategory,
# owner_suggestion, existing_controls, and priority).
RISKS_SCHEMA = {
    "title":              "TEXT",
    "description":        "TEXT",
    "category":           "TEXT",
    "nist_function":      "TEXT",
    "nist_category":      "TEXT",
    "iso_domain":         "TEXT",
    "cia_component":      "TEXT",
    "mitre_tactic":       "TEXT",
    "cis_control":        "TEXT",
    "likelihood":         "INTEGER",
    "impact":             "INTEGER",
    "risk_score":         "INTEGER DEFAULT 0",
    "owner":              "TEXT",
    "status":             "TEXT DEFAULT 'Open'",
    "mitigation":         "TEXT",
    "review_date":        "TEXT",
    "date_identified":    "TEXT",
    "date_modified":      "TEXT",
    "source":             "TEXT DEFAULT 'Manual'",
    "notes":              "TEXT",
    "ai_suggestion":      "TEXT",
    "pdf_source":         "TEXT",
    "mitre_technique":    "TEXT",
    "inherent_score":     "INTEGER DEFAULT 0",
    "residual_score":     "INTEGER DEFAULT 0",
    "risk_velocity":      "INTEGER DEFAULT 2",
    "confidence":         "TEXT",
    "iso_control":        "TEXT",
    "nist_subcategory":   "TEXT",
    "owner_suggestion":   "TEXT",
    "existing_controls":  "TEXT",
    "priority":           "TEXT",
}

def _migrate_schema():
    """
    Inspect the live 'risks' table via PRAGMA table_info and ALTER TABLE
    ADD COLUMN for anything in RISKS_SCHEMA that is missing. Makes the app
    safe to run against databases created by any older RiskCore version
    without losing existing data. Idempotent: only adds columns confirmed
    absent, so it's safe to call on every startup.
    """
    with get_db() as conn:
        existing = {row[1] for row in
                    conn.execute("PRAGMA table_info(risks)").fetchall()}
        missing = [col for col in RISKS_SCHEMA if col not in existing]
        for col in missing:
            col_def = RISKS_SCHEMA[col]
            try:
                conn.execute(f"ALTER TABLE risks ADD COLUMN {col} {col_def}")
                print(f"[migration] Added missing column: {col} ({col_def})")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        if missing:
            audit("SCHEMA_MIGRATION",
                  detail=f"Added columns: {', '.join(missing)}")

def audit(action, risk_id=None, detail=""):
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO audit_log(timestamp,action,risk_id,detail) VALUES(?,?,?,?)",
                (datetime.datetime.now().isoformat(),
                 sanitise(action, 100),
                 risk_id,
                 sanitise(str(detail), 300)))
    except Exception as e:
        print(f"[audit error] {e}")

def insert_risk(data, source="Manual"):
    try: lik = max(1, min(5, int(round(float(data.get("likelihood", 3))))))
    except: lik = 3
    try: imp = max(1, min(5, int(round(float(data.get("impact", 3))))))
    except: imp = 3
    score = lik * imp
    try: res = max(1, int(float(data.get("residual_score", max(1, score - 2)))))
    except: res = max(1, score - 2)
    try: vel = int(data.get("risk_velocity", 2))
    except: vel = 2

    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO risks(
                title, description, category, nist_function, nist_category,
                iso_domain, cia_component, mitre_tactic, cis_control,
                likelihood, impact, risk_score, inherent_score, residual_score,
                risk_velocity, owner, status, mitigation, review_date,
                date_identified, date_modified, source, notes,
                ai_suggestion, mitre_technique, confidence, iso_control,
                nist_subcategory, owner_suggestion, existing_controls, priority)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            sanitise(data.get("title", ""), 200),
            sanitise(data.get("description", ""), 1000),
            sanitise(data.get("category", "Technical"), 100),
            sanitise(data.get("nist_function", "Identify"), 100),
            sanitise(data.get("nist_category", ""), 100),
            sanitise(data.get("iso_domain", ""), 100),
            sanitise(data.get("cia_component", ""), 100),
            sanitise(data.get("mitre_tactic", "Not Applicable"), 100),
            sanitise(data.get("cis_control", "Not Applicable"), 200),
            lik, imp, score, score, res, vel,
            sanitise(data.get("owner", ""), 200),
            sanitise(data.get("status", "Open"), 50),
            sanitise(data.get("recommended_mitigation",
                               data.get("mitigation", "")), 1000),
            sanitise(data.get("review_date", ""), 10),
            today(), today(),
            sanitise(source, 50),
            sanitise(data.get("notes", ""), 500),
            sanitise(data.get("ai_suggestion", ""), 500),
            sanitise(data.get("mitre_technique", ""), 200),
            sanitise(data.get("confidence", ""), 20),
            sanitise(data.get("iso_control", ""), 100),
            sanitise(data.get("nist_subcategory", ""), 100),
            sanitise(data.get("owner_suggestion", ""), 200),
            sanitise(data.get("existing_controls", ""), 500),
            sanitise(data.get("priority", ""), 50),
        ))
        rid = cur.lastrowid

    audit("CREATE", rid, f"{source}: {str(data.get('title',''))[:60]}")
    return rid

def update_risk(rid, data):
    """
    Update an existing risk in place. Mirrors insert_risk's validation
    and sanitisation so Edit and Add stay behaviourally consistent.
    Uses a parameterised UPDATE — no string interpolation of values.
    """
    try: lik = max(1, min(5, int(round(float(data.get("likelihood", 3))))))
    except: lik = 3
    try: imp = max(1, min(5, int(round(float(data.get("impact", 3))))))
    except: imp = 3
    score = lik * imp
    try: res = max(1, int(float(data.get("residual_score", max(1, score - 2)))))
    except: res = max(1, score - 2)
    try: vel = int(data.get("risk_velocity", 2))
    except: vel = 2

    with get_db() as conn:
        conn.execute("""
            UPDATE risks SET
                title=?, description=?, category=?, nist_function=?,
                nist_category=?, iso_domain=?, cia_component=?,
                mitre_tactic=?, cis_control=?, likelihood=?, impact=?,
                risk_score=?, inherent_score=?, residual_score=?,
                risk_velocity=?, owner=?, status=?, mitigation=?,
                review_date=?, date_modified=?, notes=?, mitre_technique=?,
                confidence=?, iso_control=?, nist_subcategory=?,
                existing_controls=?, priority=?
            WHERE id=?
        """, (
            sanitise(data.get("title", ""), 200),
            sanitise(data.get("description", ""), 1000),
            sanitise(data.get("category", "Technical"), 100),
            sanitise(data.get("nist_function", "Identify"), 100),
            sanitise(data.get("nist_category", ""), 100),
            sanitise(data.get("iso_domain", ""), 100),
            sanitise(data.get("cia_component", ""), 100),
            sanitise(data.get("mitre_tactic", "Not Applicable"), 100),
            sanitise(data.get("cis_control", "Not Applicable"), 200),
            lik, imp, score, score, res, vel,
            sanitise(data.get("owner", ""), 200),
            sanitise(data.get("status", "Open"), 50),
            sanitise(data.get("mitigation", ""), 1000),
            sanitise(data.get("review_date", ""), 10),
            today(),
            sanitise(data.get("notes", ""), 500),
            sanitise(data.get("mitre_technique", ""), 200),
            sanitise(data.get("confidence", ""), 20),
            sanitise(data.get("iso_control", ""), 100),
            sanitise(data.get("nist_subcategory", ""), 100),
            sanitise(data.get("existing_controls", ""), 500),
            sanitise(data.get("priority", ""), 50),
            int(rid),
        ))
    audit("UPDATE", rid, f"Manual edit: {str(data.get('title',''))[:60]}")
    return True

def get_risks(search="", status_filter="All",
              nist_filter="All", score_filter="All"):
    query  = "SELECT * FROM risks WHERE 1=1"
    params = []
    if search:
        s = f"%{sanitise(search, 100)}%"
        query += (" AND (title LIKE ? OR description LIKE ? "
                  "OR owner LIKE ? OR mitre_tactic LIKE ?)")
        params += [s, s, s, s]
    if status_filter != "All":
        query += " AND status=?"
        params.append(sanitise(status_filter, 50))
    if nist_filter != "All":
        query += " AND nist_function=?"
        params.append(sanitise(nist_filter, 50))
    if score_filter == "Low":
        query += " AND COALESCE(risk_score,0)<=4"
    elif score_filter == "Medium":
        query += " AND COALESCE(risk_score,0) BETWEEN 5 AND 9"
    elif score_filter == "High":
        query += " AND COALESCE(risk_score,0) BETWEEN 10 AND 14"
    elif score_filter == "Critical":
        query += " AND COALESCE(risk_score,0)>=15"
    query += " ORDER BY COALESCE(risk_score,0) DESC, date_modified DESC"
    with get_db() as conn:
        return conn.execute(query, params).fetchall()

def get_risk(rid):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM risks WHERE id=?", (int(rid),)).fetchone()

def delete_risk(rid):
    with get_db() as conn:
        conn.execute("DELETE FROM risks WHERE id=?", (int(rid),))
    audit("DELETE", rid)

def get_stats():
    with get_db() as conn:
        total    = conn.execute(
            "SELECT COUNT(*) FROM risks").fetchone()[0]
        critical = conn.execute(
            "SELECT COUNT(*) FROM risks "
            "WHERE COALESCE(risk_score,0)>=15").fetchone()[0]
        high     = conn.execute(
            "SELECT COUNT(*) FROM risks "
            "WHERE COALESCE(risk_score,0) BETWEEN 10 AND 14").fetchone()[0]
        open_r   = conn.execute(
            "SELECT COUNT(*) FROM risks WHERE status='Open'").fetchone()[0]
        overdue  = conn.execute(
            "SELECT COUNT(*) FROM risks "
            "WHERE review_date!='' AND review_date IS NOT NULL "
            "AND review_date<? "
            "AND status NOT IN ('Closed','Mitigated')",
            (today(),)).fetchone()[0]
        ai_src   = conn.execute(
            "SELECT COUNT(*) FROM risks "
            "WHERE source='AI Analysis'").fetchone()[0]
    return {"total": total, "critical": critical, "high": high,
            "open": open_r, "overdue": overdue, "ai_sourced": ai_src}

def backup_database(dest_folder=None):
    """
    Create a timestamped copy of the live database file. Pure file copy
    via shutil — no schema changes, no data transformation, no risk to
    the live DB. If WAL mode has uncommitted pages still in the -wal
    file, a checkpoint is run first so the backup is a complete,
    self-contained snapshot rather than missing recent writes.
    Returns the path to the created backup file.
    """
    if dest_folder is None:
        dest_folder = BASE_DIR / "backups"
    dest_folder = Path(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)

    # Flush WAL into the main DB file so the copy is complete and
    # consistent, without altering the schema or any row.
    try:
        with get_db() as conn:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
    except Exception as e:
        print(f"[backup checkpoint warning] {e}")

    # BUG FIX (found via testing): the timestamp previously used
    # second-level precision only (%Y%m%d_%H%M%S). Two backup_database()
    # calls within the same second — which genuinely happens, e.g.
    # restore_database() takes a safety-net backup immediately before
    # overwriting the live DB, sometimes less than a second after a
    # user-triggered backup — produced an IDENTICAL destination filename,
    # silently overwriting the earlier backup with the later one. This
    # was caught by directly testing backup -> insert -> restore and
    # finding the "restored" data didn't match the original backup's
    # content: the backup file had been clobbered before the restore's
    # copy step ever ran. Fixed with microsecond-resolution timestamps
    # plus an explicit collision-avoidance suffix as a second safety net
    # in case two calls ever land in the same microsecond.
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest_path = dest_folder / f"riskcore_backup_{ts}.db"
    suffix = 1
    while dest_path.exists():
        dest_path = dest_folder / f"riskcore_backup_{ts}_{suffix}.db"
        suffix += 1
    shutil.copy2(DB_PATH, dest_path)
    audit("DB_BACKUP", detail=f"Backup created: {dest_path.name}")
    return dest_path

def restore_database(backup_path):
    """
    Restore the live database from a backup file. The current live DB
    is itself backed up first (safety net before overwriting), then the
    chosen backup file replaces riskcore.db. No schema changes are made
    — this is a straight file replacement, so the restored DB must have
    been created by a compatible version of RiskCore (the same schema
    migration that runs on every startup will still apply if needed).
    """
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    # Safety net: back up the current live DB before overwriting it,
    # so a restore can itself be undone.
    pre_restore_backup = backup_database()
    shutil.copy2(backup_path, DB_PATH)
    audit("DB_RESTORE",
          detail=f"Restored from {backup_path.name} "
                 f"(pre-restore snapshot: {pre_restore_backup.name})")
    return pre_restore_backup

# ── App ───────────────────────────────────────────────────────────────────────
class RiskCore(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("RiskCore GRC Platform v1.0")
        self.geometry("1160x780")
        self.minsize(1020, 660)
        self.configure(fg_color=DARK_BG)
        set_icon(self)
        init_db()
        audit("APP_START", detail="RiskCore launched")

        self._pending_ai_risks = []
        self._settings          = load_settings()
        self._company_name      = self._settings["organisation_name"]
        self._current_page      = "dashboard"
        self._pending_edit_id   = None
        self._api_key           = load_api_key()

        # filter state — preserved across register refreshes
        self._search_val  = ""
        self._status_val  = "All"
        self._nist_val    = "All"
        self._score_val   = "All"

        self._build_sidebar()
        self._build_main()
        self._build_statusbar()
        self.show_page("dashboard")
        self._refresh_statusbar()

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        sb = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=26)
        sb.pack(side="bottom", fill="x")
        sb.pack_propagate(False)
        self._sb_db  = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(size=10),
                                     text_color=TEXT_MUTED)
        self._sb_db.pack(side="left", padx=12)
        self._sb_total = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(size=10),
                                       text_color=TEXT_MUTED)
        self._sb_total.pack(side="left", padx=6)
        self._sb_time = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(size=10),
                                      text_color=TEXT_MUTED)
        self._sb_time.pack(side="right", padx=12)

    def _refresh_statusbar(self):
        try:
            stats = get_stats()
            db_ok = DB_PATH.exists()
            self._sb_db.configure(
                text=f"{'🟢' if db_ok else '🔴'} DB: {'Connected' if db_ok else 'ERROR'}",
                text_color=GREEN if db_ok else RED)
            self._sb_total.configure(
                text=f"│  {stats['total']} risks  ·  "
                     f"{stats['critical']} critical  ·  "
                     f"{stats['open']} open")
            self._sb_time.configure(
                text=f"Last refreshed: {now_str()}")
        except Exception as e:
            self._sb_db.configure(text=f"🔴 DB Error: {e}", text_color=RED)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, fg_color=CARD_BG, corner_radius=0)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.pack(pady=(22, 6), padx=14, fill="x")
        ctk.CTkLabel(brand, text="🔐",
                     font=ctk.CTkFont(size=28)).pack(side="left")
        nf = ctk.CTkFrame(brand, fg_color="transparent")
        nf.pack(side="left", padx=8)
        ctk.CTkLabel(nf, text="RiskCore",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w")
        ctk.CTkLabel(nf, text="GRC Platform v1.0",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_MUTED).pack(anchor="w")

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=6)

        self.nav_btns = {}
        pages = [
            ("dashboard", "📊", "Dashboard"),
            ("ai",        "🤖", "AI Analysis"),
            ("register",  "📋", "Risk Register"),
            ("add",       "➕", "Add Risk"),
            ("matrix",    "🎯", "Risk Matrix"),
            ("export",    "📤", "Export & Report"),
            ("audit",     "🔍", "Audit Log"),
            ("settings",  "⚙️", "Settings"),
        ]
        for key, icon, label in pages:
            btn = ctk.CTkButton(
                sb, text=f"{icon}  {label}", anchor="w", height=38,
                font=ctk.CTkFont(size=12), fg_color="transparent",
                hover_color="#1C2128", text_color=TEXT_MUTED,
                corner_radius=6,
                command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", padx=8, pady=1)
            self.nav_btns[key] = btn

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=6)

        for fw, color in [
            ("NIST CSF 2.0",    "#1D4ED8"),
            ("ISO 27001:2022",  "#16A34A"),
            ("MITRE ATT&CK",    "#DC2626"),
            ("CIS Controls v8", "#CA8A04"),
            ("CIA Triad",       "#7C3AED"),
        ]:
            f = ctk.CTkFrame(sb, fg_color=color, corner_radius=4, height=20)
            f.pack(fill="x", padx=10, pady=1)
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=fw,
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color="white").pack(padx=6, anchor="w")

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=6)
        self._pending_badge = ctk.CTkLabel(
            sb, text="", font=ctk.CTkFont(size=10), text_color=GOLD)
        self._pending_badge.pack(padx=14, anchor="w")

    # ── Main area ─────────────────────────────────────────────────────────────
    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=0)
        self.main.pack(side="right", fill="both", expand=True)

    def _clear(self):
        for w in self.main.winfo_children():
            w.destroy()

    def show_page(self, page, edit_id=None):
        self._current_page = page
        self._pending_edit_id = edit_id  # consumed by _pg_add_manual, then cleared
        for k, b in self.nav_btns.items():
            b.configure(
                fg_color=ACCENT if k == page else "transparent",
                text_color=TEXT_MAIN if k == page else TEXT_MUTED)
        self._clear()
        {
            "dashboard": self._pg_dashboard,
            "ai":        self._pg_ai,
            "register":  self._pg_register,
            "add":       self._pg_add_manual,
            "matrix":    self._pg_matrix,
            "export":    self._pg_export,
            "audit":     self._pg_audit,
            "settings":  self._pg_settings,
        }[page]()
        self._refresh_statusbar()

    def show_page_with_arg(self, page, edit_id=None):
        """Convenience wrapper so call sites read clearly: navigate to a
        page while passing through an edit target (currently only used
        for routing to the Edit Risk form)."""
        self.show_page(page, edit_id=edit_id)

    # ── Shared widgets ────────────────────────────────────────────────────────
    def _hdr(self, title, sub="", refresh_cmd=None):
        f = ctk.CTkFrame(self.main, fg_color="transparent")
        f.pack(fill="x", padx=22, pady=(16, 4))
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text=title,
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        if sub:
            ctk.CTkLabel(f, text=sub,
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).grid(row=1, column=0, sticky="w")
        if refresh_cmd:
            ctk.CTkButton(f, text="⟳  Refresh", width=90, height=28,
                          fg_color=BORDER, hover_color="#2D3748",
                          font=ctk.CTkFont(size=11), corner_radius=6,
                          command=refresh_cmd).grid(row=0, column=1,
                          padx=(8, 0), sticky="e")

    def _stat_card(self, parent, row, col, title, val, sub="", color=TEXT_MAIN):
        f = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=10)
        f.grid(row=row, column=col, padx=7, pady=7, sticky="nsew")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(pady=(12, 2), padx=14, anchor="w")
        ctk.CTkLabel(f, text=str(val),
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=color).pack(padx=14, anchor="w")
        ctk.CTkLabel(f, text=sub or " ", font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(padx=14, pady=(0, 12), anchor="w")

    def _toast(self, msg, color=GREEN, duration=4000):
        """Non-blocking notification bar that auto-dismisses."""
        if hasattr(self, "_toast_widget") and self._toast_widget.winfo_exists():
            self._toast_widget.destroy()
        t = ctk.CTkFrame(self.main, fg_color=color, corner_radius=8, height=36)
        t.pack(fill="x", padx=18, pady=(0, 4))
        t.pack_propagate(False)
        ctk.CTkLabel(t, text=msg, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="white").pack(padx=14, pady=6, anchor="w")
        self._toast_widget = t
        self.after(duration, lambda: t.destroy() if t.winfo_exists() else None)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    def _pg_dashboard(self):
        self._hdr("📊  Dashboard",
                  f"RiskCore GRC  ·  {today()}  ·  "
                  "NIST CSF 2.0 | ISO/IEC 27001:2022 | MITRE ATT&CK | CIS Controls v8 | CIA Triad",
                  refresh_cmd=lambda: self.show_page("dashboard"))

        stats = get_stats()
        g = ctk.CTkFrame(self.main, fg_color="transparent")
        g.pack(fill="x", padx=18, pady=(4, 0))
        for i in range(6):
            g.grid_columnconfigure(i, weight=1)

        self._stat_card(g, 0, 0, "Total Risks",  stats["total"],      "in register")
        self._stat_card(g, 0, 1, "Critical",      stats["critical"],   "score ≥ 15",   RED)
        self._stat_card(g, 0, 2, "High",          stats["high"],       "score 10–14",  ORANGE)
        self._stat_card(g, 0, 3, "Open",          stats["open"],       "unresolved",   GOLD)
        self._stat_card(g, 0, 4, "Overdue",       stats["overdue"],    "past review",
                        RED if stats["overdue"] else TEXT_MUTED)
        self._stat_card(g, 0, 5, "AI Sourced",    stats["ai_sourced"], "from PDF",     PURPLE)

        # Pending AI banner
        if self._pending_ai_risks:
            pb = ctk.CTkFrame(self.main, fg_color="#1C1C2E", corner_radius=8)
            pb.pack(fill="x", padx=18, pady=(8, 0))
            ctk.CTkLabel(
                pb,
                text=f"🤖  {len(self._pending_ai_risks)} AI-suggested risks awaiting review",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=GOLD).pack(side="left", padx=14, pady=10)
            ctk.CTkButton(
                pb, text="Review Now →", fg_color=PURPLE, height=28,
                font=ctk.CTkFont(size=11), corner_radius=6,
                command=lambda: self.show_page("ai")).pack(
                side="right", padx=14, pady=10)

        # NIST breakdown
        ctk.CTkLabel(self.main, text="Risk Distribution by NIST CSF Function",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=22, pady=(16, 4))
        nf = ctk.CTkFrame(self.main, fg_color=CARD_BG, corner_radius=10)
        nf.pack(fill="x", padx=18, pady=(0, 8))
        nf.grid_columnconfigure(1, weight=1)
        nist_colors = {
            "Identify": "#1D4ED8", "Protect":  "#16A34A",
            "Detect":   "#CA8A04", "Respond":  "#EA580C", "Recover": "#7C3AED",
        }
        total_safe = max(stats["total"], 1)
        with get_db() as conn:
            for i, fn in enumerate(NIST_FUNCTIONS):
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM risks WHERE nist_function=?",
                    (fn,)).fetchone()[0]
                avg = conn.execute(
                    "SELECT AVG(COALESCE(risk_score,0)) FROM risks "
                    "WHERE nist_function=?", (fn,)).fetchone()[0]
                avg = round(avg, 1) if avg else 0
                color = nist_colors.get(fn, ACCENT)
                ctk.CTkLabel(nf, text=fn, font=ctk.CTkFont(size=11),
                             text_color=color, width=90,
                             anchor="w").grid(row=i, column=0,
                             padx=(14, 8), pady=5, sticky="w")
                bar = ctk.CTkProgressBar(nf, height=10, corner_radius=4,
                                          progress_color=color, fg_color=BORDER)
                bar.set(min(cnt / total_safe, 1.0))
                bar.grid(row=i, column=1, padx=4, pady=5, sticky="ew")
                ctk.CTkLabel(nf, text=f"{cnt} risks · avg {avg}",
                             font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
                             width=120, anchor="e").grid(
                             row=i, column=2, padx=(8, 14), pady=5, sticky="e")

        # Top critical risks
        risks = get_risks(score_filter="Critical")[:5]
        if risks:
            ctk.CTkLabel(self.main, text="🔴  Top Critical Risks",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=TEXT_MAIN).pack(
                         anchor="w", padx=22, pady=(16, 4))
            tf = ctk.CTkFrame(self.main, fg_color=CARD_BG, corner_radius=10)
            tf.pack(fill="x", padx=18, pady=(0, 16))
            tf.grid_columnconfigure(1, weight=1)
            for i, r in enumerate(risks):
                sc = int(r["risk_score"] or 0)
                ctk.CTkLabel(tf, text=f"{score_label(sc)} {sc}",
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=score_color(sc),
                             width=80).grid(row=i, column=0,
                             padx=(10, 6), pady=5, sticky="w")
                ctk.CTkLabel(tf, text=r["title"],
                             font=ctk.CTkFont(size=11),
                             text_color=TEXT_MAIN,
                             anchor="w").grid(row=i, column=1, pady=5, sticky="w")
                # BUG FIX: sqlite3.Row objects do not support .get() the
                # way dicts do — calling r.get("source") here raised
                # AttributeError, which silently aborted rendering of
                # this entire frame (and anything after it) since Tk
                # swallows exceptions raised inside its callback/render
                # path and just prints a traceback rather than crashing
                # the whole app. Fixed by reading the column directly and
                # falling back to "Manual" only when the value is falsy
                # (None / empty string), which sqlite3.Row supports via
                # plain key access since every row.keys() column exists
                # even when its value is NULL.
                src_val = r["source"] or "Manual"
                src_color = PURPLE if src_val == "AI Analysis" else TEXT_MUTED
                ctk.CTkLabel(tf, text=src_val,
                             font=ctk.CTkFont(size=10),
                             text_color=src_color).grid(
                             row=i, column=2, padx=6, pady=5)
                ctk.CTkLabel(tf, text=r["nist_function"] or "—",
                             font=ctk.CTkFont(size=10),
                             text_color=TEXT_MUTED).grid(
                             row=i, column=3, padx=6, pady=5)
                ctk.CTkLabel(tf, text=r["status"],
                             font=ctk.CTkFont(size=10),
                             text_color=GOLD if r["status"] == "Open" else GREEN).grid(
                             row=i, column=4, padx=(6, 12), pady=5)
        elif stats["total"] == 0:
            ctk.CTkLabel(
                self.main,
                text="No risks yet.\n"
                     "Go to ➕ Add Risk to log manually, "
                     "or 🤖 AI Analysis to upload a document.",
                font=ctk.CTkFont(size=13), text_color=TEXT_MUTED,
                justify="center").pack(expand=True)

    # ── AI Analysis ───────────────────────────────────────────────────────────
    def _pg_ai(self):
        self._hdr("🤖  AI Risk Analysis",
                  "Upload a PDF · AI analyses all 5 frameworks · Review & approve")

        scroll = ctk.CTkScrollableFrame(self.main, fg_color=DARK_BG)
        scroll.pack(fill="both", expand=True)

        # API key
        kf = ctk.CTkFrame(scroll, fg_color="#1C1C2E", corner_radius=10)
        kf.pack(fill="x", padx=18, pady=(4, 8))
        kf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(kf, text="🔑  Anthropic API Key",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=PURPLE).grid(
                     row=0, column=0, columnspan=3,
                     padx=14, pady=(12, 4), sticky="w")
        ctk.CTkLabel(kf,
                     text="Get your key at console.anthropic.com → API Keys  "
                          "(starts with sk-ant-api03-)",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, columnspan=3,
                     padx=14, pady=(0, 6), sticky="w")
        self._key_var = ctk.StringVar(value=self._api_key)
        ctk.CTkEntry(kf, textvariable=self._key_var,
                     show="•", font=ctk.CTkFont(size=12),
                     placeholder_text="sk-ant-api03-...").grid(
                     row=2, column=0, columnspan=2,
                     padx=(14, 8), pady=(0, 12), sticky="ew")
        key_status_lbl = ctk.CTkLabel(
            kf,
            text="✅ Key loaded" if self._api_key else "⚠ No key — enter above",
            font=ctk.CTkFont(size=10),
            text_color=GREEN if self._api_key else GOLD)
        key_status_lbl.grid(row=3, column=0, columnspan=3,
                            padx=14, pady=(0, 10), sticky="w")

        def save_key():
            k = self._key_var.get().strip()
            if not k.startswith("sk-ant"):
                messagebox.showerror(
                    "Invalid Key",
                    "Key should start with 'sk-ant-api03-'\n"
                    "Get yours at: console.anthropic.com → API Keys")
                return
            self._api_key = k
            save_api_key(k)
            key_status_lbl.configure(text="✅ Key saved", text_color=GREEN)

        ctk.CTkButton(kf, text="Save", width=80, height=28,
                      fg_color=PURPLE, font=ctk.CTkFont(size=11),
                      corner_radius=6, command=save_key).grid(
                      row=2, column=2, padx=(0, 14), pady=(0, 12))

        # Company name
        cf = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        cf.pack(fill="x", padx=18, pady=(0, 8))
        cf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(cf, text="Organisation Name",
                     font=ctk.CTkFont(size=12),
                     text_color=TEXT_MUTED).grid(
                     row=0, column=0, padx=14, pady=12, sticky="w")
        self._cn_var = ctk.StringVar(value=self._company_name)
        ctk.CTkEntry(cf, textvariable=self._cn_var,
                     font=ctk.CTkFont(size=12),
                     placeholder_text="Company name for the report").grid(
                     row=0, column=1, padx=14, pady=12, sticky="ew")

        # PDF upload
        uf = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        uf.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(uf, text="📄  Upload Document",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).pack(padx=14, pady=(12, 4), anchor="w")
        ctk.CTkLabel(
            uf,
            text="Supported: PDF  ·  Security policies, audit reports, "
                 "incident reports, vendor assessments, compliance docs",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED).pack(padx=14, pady=(0, 8), anchor="w")
        self._pdf_path_var = ctk.StringVar(value="No file selected")
        pr = ctk.CTkFrame(uf, fg_color="transparent")
        pr.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(pr, textvariable=self._pdf_path_var,
                     font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
                     wraplength=580, anchor="w").pack(
                     side="left", fill="x", expand=True)
        ctk.CTkButton(pr, text="Browse PDF", width=100, height=30,
                      fg_color=ACCENT2, font=ctk.CTkFont(size=11),
                      corner_radius=6,
                      command=self._browse_pdf).pack(side="right")

        # Classification
        of = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        of.pack(fill="x", padx=18, pady=(0, 8))
        of.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(of, text="Report Classification",
                     font=ctk.CTkFont(size=12),
                     text_color=TEXT_MUTED).grid(
                     row=0, column=0, padx=14, pady=10, sticky="w")
        self._classif_var = ctk.StringVar(value="CONFIDENTIAL")
        ctk.CTkOptionMenu(of, variable=self._classif_var,
                          values=["CONFIDENTIAL","RESTRICTED",
                                  "INTERNAL","PUBLIC"],
                          fg_color=BORDER, button_color=ACCENT,
                          font=ctk.CTkFont(size=11)).grid(
                          row=0, column=1, padx=14, pady=10, sticky="w")

        # Status/progress
        self._ai_status_var = ctk.StringVar(
            value="Ready — enter API key and select a PDF")
        sf = ctk.CTkFrame(scroll, fg_color="#1C1C2E", corner_radius=10)
        sf.pack(fill="x", padx=18, pady=(0, 8))
        self._ai_status_lbl = ctk.CTkLabel(
            sf, textvariable=self._ai_status_var,
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self._ai_status_lbl.pack(padx=14, pady=8, anchor="w")
        self._ai_progress = ctk.CTkProgressBar(
            sf, height=6, progress_color=PURPLE, fg_color=BORDER)
        self._ai_progress.set(0)
        self._ai_progress.pack(fill="x", padx=14, pady=(0, 10))

        self._analyse_btn = ctk.CTkButton(
            scroll, text="🤖  Analyse Document with AI",
            height=46, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=PURPLE, hover_color="#6D28D9", corner_radius=10,
            command=self._start_analysis)
        self._analyse_btn.pack(fill="x", padx=18, pady=(0, 12))

        if self._pending_ai_risks:
            self._render_ai_results(scroll)

    def _browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Select PDF Document",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")])
        if path:
            self._pdf_path_var.set(path)

    def _start_analysis(self):
        if not self._api_key:
            messagebox.showerror(
                "API Key Required",
                "Please enter your Anthropic API key first.\n\n"
                "Get it at: console.anthropic.com → API Keys\n"
                "It starts with: sk-ant-api03-")
            return
        pdf_path = self._pdf_path_var.get()
        if pdf_path == "No file selected" or not os.path.exists(pdf_path):
            messagebox.showerror("No File", "Please select a PDF file first.")
            return
        self._company_name = self._cn_var.get().strip() or "Your Organisation"
        self._analyse_btn.configure(state="disabled",
                                    text="⏳  Analysing...")
        self._ai_progress.set(0.1)
        self._ai_status_var.set("Extracting text from PDF...")
        self._ai_status_lbl.configure(text_color=GOLD)
        api_key = self._api_key

        def run():
            try:
                from riskcore_ai import extract_pdf_text, build_analysis_prompt

                def progress(msg):
                    self.after(0, lambda m=msg: self._ai_status_var.set(m))
                    steps = {"extracting": 0.2, "sending": 0.4,
                             "ai is": 0.6, "parsing": 0.9}
                    for k, v in steps.items():
                        if k in msg.lower():
                            self.after(0, lambda vv=v:
                                       self._ai_progress.set(vv))
                            break

                progress("Extracting text from PDF...")
                text = extract_pdf_text(pdf_path)
                if text.startswith("ERROR"):
                    raise RuntimeError(text)
                progress("Sending to AI (20–40 seconds)...")
                prompt = build_analysis_prompt(text, self._company_name)
                result = self._call_api(prompt, api_key, progress)
                self._last_analysis    = result
                self._last_pdf_path    = pdf_path
                self._pending_ai_risks = result.get("risks", [])

                def done():
                    self._ai_progress.set(1.0)
                    n = len(self._pending_ai_risks)
                    self._ai_status_var.set(
                        f"✅  Analysis complete — {n} risks found")
                    self._ai_status_lbl.configure(text_color=GREEN)
                    self._analyse_btn.configure(
                        state="normal",
                        text="🤖  Analyse Document with AI")
                    self._pending_badge.configure(
                        text=f"🟡 {n} risks pending review")
                    audit("AI_ANALYSIS",
                          detail=f"PDF: {Path(pdf_path).name} → "
                                 f"{n} risks, posture: "
                                 f"{result.get('overall_risk_posture','?')}")
                    self.show_page("ai")
                self.after(0, done)

            except Exception as e:
                def err(msg=str(e)):
                    self._ai_status_var.set(f"⚠  Error: {msg}")
                    self._ai_status_lbl.configure(text_color=RED)
                    self._analyse_btn.configure(
                        state="normal",
                        text="🤖  Analyse Document with AI")
                    self._ai_progress.set(0)
                self.after(0, err)

        threading.Thread(target=run, daemon=True).start()

    def _call_api(self, prompt, api_key, progress=None):
        import urllib.request, urllib.error
        if progress:
            progress("AI is analysing all 5 frameworks...")
        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        text = "".join(b.get("text", "") for b in raw.get("content", [])
                       if b.get("type") == "text")
        text = re.sub(r'^```[a-z]*\n?', '', text.strip())
        text = re.sub(r'\n?```$', '', text.strip())
        return json.loads(text)

    def _render_ai_results(self, parent):
        ctk.CTkLabel(
            parent,
            text=f"📋  AI Found {len(self._pending_ai_risks)} Risks"
                 " — Review & Approve",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_MAIN).pack(anchor="w", padx=18, pady=(8, 4))

        analysis = getattr(self, "_last_analysis", {})
        if analysis.get("analyst_summary"):
            sf = ctk.CTkFrame(parent, fg_color="#1C2820", corner_radius=8)
            sf.pack(fill="x", padx=18, pady=(0, 8))
            ctk.CTkLabel(sf,
                         text=f"AI Summary: {analysis['analyst_summary']}",
                         font=ctk.CTkFont(size=11), text_color=GREEN,
                         wraplength=860, justify="left").pack(
                         padx=12, pady=10, anchor="w")

        self._risk_checks = {}
        for i, risk in enumerate(self._pending_ai_risks):
            inh = int(risk.get(
                "inherent_score",
                risk.get("likelihood", 1) * risk.get("impact", 1)) or 1)
            rf = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=10)
            rf.pack(fill="x", padx=18, pady=3)
            rf.grid_columnconfigure(2, weight=1)

            var = ctk.BooleanVar(value=True)
            self._risk_checks[i] = var
            ctk.CTkCheckBox(rf, variable=var, text="", width=24).grid(
                row=0, column=0, padx=(10, 4), pady=10)
            ctk.CTkLabel(rf,
                         text=f"{score_label(inh)}\n{inh}",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=score_color(inh), width=60,
                         justify="center").grid(
                         row=0, column=1, padx=4, pady=10, sticky="w")

            info = ctk.CTkFrame(rf, fg_color="transparent")
            info.grid(row=0, column=2, padx=4, pady=6, sticky="ew")
            info.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(info, text=risk.get("title", ""),
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=TEXT_MAIN,
                         anchor="w").grid(row=0, column=0, sticky="w")
            meta = (f"NIST: {risk.get('nist_function','')} › "
                    f"{risk.get('nist_category','')}  ·  "
                    f"ISO: {risk.get('iso_domain','')}  ·  "
                    f"MITRE: {risk.get('mitre_tactic','N/A')}  ·  "
                    f"CIS: {risk.get('cis_control','N/A')}  ·  "
                    f"CIA: {risk.get('cia_component','')}  ·  "
                    f"Confidence: {risk.get('confidence','')}")
            ctk.CTkLabel(info, text=meta, font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED, anchor="w",
                         wraplength=680).grid(row=1, column=0, sticky="w")
            desc = str(risk.get("description") or "")
            ctk.CTkLabel(info,
                         text=desc[:120] + ("..." if len(desc) > 120 else ""),
                         font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
                         anchor="w", wraplength=680).grid(
                         row=2, column=0, sticky="w", pady=(2, 4))

            vel_map = {1: "🟢 Slow", 2: "🟡 Medium",
                       3: "🟠 Fast", 4: "🔴 Immediate"}
            ctk.CTkLabel(
                rf,
                text=(f"L:{risk.get('likelihood','')} "
                      f"I:{risk.get('impact','')}  ·  "
                      f"Res:{risk.get('residual_score','?')}  ·  "
                      f"{vel_map.get(risk.get('risk_velocity', 2), '?')}  ·  "
                      f"{risk.get('priority','')}"),
                font=ctk.CTkFont(size=10),
                text_color=TEXT_MUTED).grid(
                row=0, column=3, padx=8, pady=10)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(8, 4))
        ctk.CTkButton(btn_row,
                      text="✅  Approve Selected & Add to Register",
                      height=42, fg_color=GREEN,
                      font=ctk.CTkFont(size=13), corner_radius=8,
                      command=self._approve_risks).pack(
                      side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="🗑  Discard All",
                      height=42, fg_color="#3D1515",
                      hover_color="#7F1D1D",
                      font=ctk.CTkFont(size=13), corner_radius=8,
                      command=self._discard_ai).pack(side="left")

    def _approve_risks(self):
        approved = [self._pending_ai_risks[i]
                    for i, v in self._risk_checks.items() if v.get()]
        if not approved:
            messagebox.showinfo("None Selected",
                                "Select at least one risk to approve.")
            return
        pdf_name = Path(
            getattr(self, "_last_pdf_path", "unknown.pdf")).name
        for risk in approved:
            risk["ai_suggestion"] = f"AI-identified from: {pdf_name}"
            insert_risk(risk, source="AI Analysis")
        self._pending_ai_risks = []
        self._pending_badge.configure(text="")
        audit("AI_APPROVE",
              detail=f"{len(approved)} risks approved from {pdf_name}")
        self._refresh_statusbar()
        # navigate to register so user sees the new risks immediately
        self.show_page("register")
        self._toast(f"✅  {len(approved)} AI risk(s) added to register")

    def _discard_ai(self):
        if messagebox.askyesno("Discard", "Discard all AI suggestions?"):
            self._pending_ai_risks = []
            self._pending_badge.configure(text="")
            self.show_page("ai")

    # ── Risk Register ─────────────────────────────────────────────────────────
    def _pg_register(self):
        self._hdr("📋  Risk Register",
                  "All risks · click a row to view · colour-coded by severity",
                  refresh_cmd=self._load_reg)

        # Filter bar
        fb = ctk.CTkFrame(self.main, fg_color=CARD_BG, corner_radius=10)
        fb.pack(fill="x", padx=18, pady=(4, 6))

        # Restore filter state
        self._search_var  = ctk.StringVar(value=self._search_val)
        self._status_filt = ctk.StringVar(value=self._status_val)
        self._nist_filt   = ctk.StringVar(value=self._nist_val)
        self._score_filt  = ctk.StringVar(value=self._score_val)

        row1 = ctk.CTkFrame(fb, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(row1, text="🔍").pack(side="left", padx=(0, 4))
        se = ctk.CTkEntry(row1, textvariable=self._search_var,
                          placeholder_text="Search title, owner, MITRE tactic...",
                          font=ctk.CTkFont(size=12), height=32)
        se.pack(side="left", fill="x", expand=True, padx=(0, 8))
        se.bind("<KeyRelease>", lambda e: self._save_filters_and_reload())

        row2 = ctk.CTkFrame(fb, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(0, 8))
        for lbl, var, vals in [
            ("Status:", self._status_filt, ["All"] + RISK_STATUS),
            ("NIST:",   self._nist_filt,   ["All"] + NIST_FUNCTIONS),
            ("Score:",  self._score_filt,
             ["All", "Low", "Medium", "High", "Critical"]),
        ]:
            ctk.CTkLabel(row2, text=lbl, font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).pack(side="left", padx=(0, 3))
            ctk.CTkOptionMenu(
                row2, variable=var, values=vals, width=120,
                fg_color=BORDER, button_color=ACCENT2,
                font=ctk.CTkFont(size=11),
                command=lambda v: self._save_filters_and_reload()).pack(
                side="left", padx=(0, 10))

        # Clear filters button
        ctk.CTkButton(row2, text="✕ Clear", width=70, height=26,
                      fg_color=BORDER, hover_color="#2D3748",
                      font=ctk.CTkFont(size=10), corner_radius=5,
                      command=self._clear_filters).pack(side="left", padx=4)

        # Column headers — widths must match COL_WIDTHS used in _load_reg
        # so the header lines up with the data rows below it.
        hf = ctk.CTkFrame(self.main, fg_color=BORDER,
                           corner_radius=0, height=28)
        hf.pack(fill="x", padx=18)
        hf.pack_propagate(False)
        header_cols = [
            ("Score", 65), ("Title", 0), ("NIST", 90),
            ("CIA", 100), ("MITRE", 110),
            ("Owner", 100), ("Status", 80), ("Src", 55),
        ]
        for col, (h, w) in enumerate(header_cols):
            hf.grid_columnconfigure(col, weight=1 if col == 1 else 0,
                                     minsize=w)
            ctk.CTkLabel(hf, text=h,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=TEXT_MUTED,
                         anchor="w").grid(
                         row=0, column=col, padx=5, pady=3, sticky="w")

        # BUG: previously the timestamp label was packed AFTER
        # self._reg_scroll (which has expand=True), both into the same
        # parent (self.main) with no explicit `side`. Tk's pack manager
        # processes children in pack-call order — packing a second
        # sibling after an expand=True sibling forces that first widget's
        # allocated space to be recalculated to make room for the new
        # one. Because CTkScrollableFrame is a composite widget (an outer
        # frame wrapping an internal canvas), this could squeeze its
        # rendered height down to near zero, especially right after
        # creation with no rows yet — hiding every row inserted into it
        # by _load_reg() even though the widgets were created correctly.
        # Fix: pack the timestamp label FIRST, anchored to the bottom,
        # so it claims its small fixed slice of vertical space up front.
        # Then pack the scrollable frame with expand=True — it now
        # unambiguously receives all space that remains, with nothing
        # packed afterward to renegotiate it down.
        self._reg_timestamp = ctk.CTkLabel(
            self.main, text=f"Last refreshed: {now_str()}",
            font=ctk.CTkFont(size=9), text_color=TEXT_MUTED)
        self._reg_timestamp.pack(side="bottom", anchor="e",
                                 padx=20, pady=(0, 4))

        self._reg_scroll = ctk.CTkScrollableFrame(
            self.main, fg_color=DARK_BG)
        self._reg_scroll.pack(side="top", fill="both", expand=True,
                              padx=18, pady=(0, 8))
        self._reg_scroll.grid_columnconfigure(1, weight=1)

        self._load_reg()

    def _save_filters_and_reload(self):
        """Persist filter state so it survives page re-renders."""
        self._search_val = self._search_var.get()
        self._status_val = self._status_filt.get()
        self._nist_val   = self._nist_filt.get()
        self._score_val  = self._score_filt.get()
        self._load_reg()

    def _clear_filters(self):
        self._search_val = ""
        self._status_val = "All"
        self._nist_val   = "All"
        self._score_val  = "All"
        self._search_var.set("")
        self._status_filt.set("All")
        self._nist_filt.set("All")
        self._score_filt.set("All")
        self._load_reg()

    def _load_reg(self):
        print("LOAD_REG CALLED")
        for w in self._reg_scroll.winfo_children():
            w.destroy()

        risks = get_risks(
            search=self._search_var.get(),
            status_filter=self._status_filt.get(),
            nist_filter=self._nist_filt.get(),
            score_filter=self._score_filt.get())
        print("RISKS FOUND:", len(risks))

        if hasattr(self, "_reg_timestamp"):
            self._reg_timestamp.configure(
                text=f"Last refreshed: {now_str()}  · "
                     f" {len(risks)} risk(s) shown")

        if not risks:
            filters_active = (
                self._search_var.get().strip() != "" or
                self._status_filt.get() != "All" or
                self._nist_filt.get() != "All" or
                self._score_filt.get() != "All")
            if filters_active:
                empty_title = "No risks match the current filters"
                empty_sub = "Try adjusting or clearing your search and filter criteria."
            else:
                empty_title = "No risks in the register yet"
                empty_sub = "Use ➕ Add Risk or 🤖 AI Analysis to get started."
            ef = ctk.CTkFrame(self._reg_scroll, fg_color="transparent")
            ef.grid(row=0, column=0, columnspan=8, pady=40)
            ctk.CTkLabel(ef, text=empty_title,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=TEXT_MAIN,
                         justify="center").pack(pady=(0, 4))
            ctk.CTkLabel(ef, text=empty_sub,
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED,
                         justify="center").pack()
            return

        # Column width plan shared by header row and every body row, so
        # everything lines up. Column 1 (Title) is the only flexible one.
        COL_WIDTHS = [65, 0, 90, 100, 110, 100, 80, 55]

        self._reg_scroll.grid_columnconfigure(1, weight=1)
        for i, r in enumerate(risks):
            print("ROW:", r["id"], r["title"])
            sc = int(r["risk_score"] or 0)
            bg = CARD_BG if i % 2 == 0 else "#1A2030"
            rf = ctk.CTkFrame(self._reg_scroll, fg_color=bg, corner_radius=5)
            rf.grid(row=i, column=0, columnspan=8,
                    sticky="ew", padx=0, pady=1)
            # BUG FIX: grid_propagate(False) was previously set on `rf`
            # with no explicit width ever given to `rf` itself. That
            # disables auto-sizing-to-fit-children, but since nothing else
            # set a width, the frame collapsed to ~0px and clipped every
            # label inside it — rows existed (hence correct counts
            # everywhere else) but were visually invisible. Letting the
            # frame size itself naturally (default propagate=True) fixes
            # this; child label widths below still control column layout.
            for col, w in enumerate(COL_WIDTHS):
                rf.grid_columnconfigure(col, weight=1 if col == 1 else 0,
                                         minsize=w)
            click = lambda e, rid=r["id"]: self._view_risk(rid)
            # CONFIRMED BUG (from live traceback): sqlite3.Row has no
            # .get() method — r.get("source") raised AttributeError here,
            # which aborted this entire render pass after only the first
            # row's print() statement ran. Tk's callback wrapper caught
            # the exception and printed a traceback instead of crashing
            # outright, which is why the page appeared silently blank
            # rather than visibly erroring in the GUI itself. Fixed by
            # reading the column directly via r["source"], which works
            # on sqlite3.Row for any column that exists in the table
            # (including NULL values, which come back as None).
            src_val = r["source"] or "Manual"
            src_color = PURPLE if src_val == "AI Analysis" else TEXT_MUTED
            mitre = r["mitre_tactic"] or "—"
            cells = [
                (f"{score_label(sc)} {sc}", score_color(sc), 0),
                (r["title"][:38],           TEXT_MAIN,       1),
                (r["nist_function"] or "—", TEXT_MUTED,      2),
                (r["cia_component"] or "—", PURPLE,          3),
                (mitre[:14],                RED,             4),
                (r["owner"] or "—",         TEXT_MUTED,      5),
                (r["status"],
                 GOLD if r["status"] == "Open" else GREEN,   6),
                (src_val[:3],
                 src_color,                                  7),
            ]
            for text, color, col in cells:
                lbl = ctk.CTkLabel(rf, text=text,
                                   font=ctk.CTkFont(size=11),
                                   text_color=color, anchor="w")
                lbl.grid(row=0, column=col, padx=5, pady=6, sticky="w")
                lbl.bind("<Button-1>", click)
            rf.bind("<Button-1>", click)
        print("ROW WIDGETS CREATED:",
              len(self._reg_scroll.winfo_children()),
              "child frames now in _reg_scroll")

    def _view_risk(self, rid):
        r = get_risk(rid)
        if not r:
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Risk #{rid} — {r['title'][:40]}")
        win.geometry("760x700")
        win.configure(fg_color=DARK_BG)
        win.grab_set()
        set_icon(win)

        sc = int(r["risk_score"] or 0)
        hband = ctk.CTkFrame(win, fg_color=score_color(sc),
                              corner_radius=0, height=48)
        hband.pack(fill="x")
        hband.pack_propagate(False)
        ctk.CTkLabel(
            hband,
            text=f"  {score_label(sc)} · Score {sc} · {r['title']}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="white").pack(side="left", padx=12, pady=8)
        # BUG FIX: sqlite3.Row has no .get() — see _load_reg comment above
        # for the full explanation. Same fix applied throughout this
        # method: direct key access (r["col"]) instead of r.get("col").
        if (r["source"] or "Manual") == "AI Analysis":
            ctk.CTkLabel(hband, text=" 🤖 AI",
                         font=ctk.CTkFont(size=11),
                         text_color="white").pack(side="right", padx=12)

        scroll = ctk.CTkScrollableFrame(win, fg_color=DARK_BG)
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(1, weight=1)

        def row(idx, lbl, val, color=TEXT_MAIN):
            ctk.CTkLabel(scroll, text=lbl,
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED,
                         width=160, anchor="w").grid(
                         row=idx, column=0,
                         padx=(14, 6), pady=3, sticky="w")
            ctk.CTkLabel(scroll, text=str(val or "—"),
                         font=ctk.CTkFont(size=11),
                         text_color=color, anchor="w",
                         wraplength=520).grid(
                         row=idx, column=1,
                         padx=(0, 14), pady=3, sticky="w")

        lik = r["likelihood"] or 1
        imp = r["impact"]     or 1
        fields = [
            ("Title",             r["title"]),
            ("Description",       r["description"]),
            ("Category",          r["category"]),
            ("Likelihood",        f"{lik} — {LIKELIHOOD_LBL.get(lik,'')}"),
            ("Impact",            f"{imp} — {IMPACT_LBL.get(imp,'')}"),
            ("Inherent Score",    f"{r['inherent_score'] or sc} "
                                  f"({score_label(sc)})"),
            ("Residual Score",    r["residual_score"] or "—"),
            ("Risk Velocity",     {1:"Slow",2:"Medium",3:"Fast",
                                   4:"Immediate"}.get(
                                   r["risk_velocity"] or 2, "—")),
            ("NIST CSF",          f"{r['nist_function']} › "
                                  f"{r['nist_category']} "
                                  f"[{r['nist_subcategory'] or ''}]"),
            ("ISO 27001",         f"{r['iso_domain']} · "
                                  f"{r['iso_control'] or ''}"),
            ("MITRE ATT&CK",      f"Tactic: {r['mitre_tactic']} | "
                                  f"Technique: "
                                  f"{r['mitre_technique'] or 'N/A'}"),
            ("CIS Control",       r["cis_control"]),
            ("CIA Component",     r["cia_component"]),
            ("Owner",             r["owner"]),
            ("Status",            r["status"]),
            ("Priority",          r["priority"] or "—"),
            ("Confidence",        r["confidence"] or "—"),
            ("Existing Controls", r["existing_controls"] or
                                  "None documented"),
            ("Mitigation Plan",   r["mitigation"]),
            ("Review Date",       r["review_date"]),
            ("Created Date",      r["date_identified"] or "—"),
            ("Last Modified",     r["date_modified"] or "—"),
            ("Source",            r["source"] or "Manual"),
            ("AI Notes",          r["ai_suggestion"] or "—"),
            ("Notes",             r["notes"]),
        ]
        for idx, (lbl, val) in enumerate(fields):
            color = score_color(sc) if "Score" in lbl else TEXT_MAIN
            row(idx, lbl, val, color)

        btn_row = ctk.CTkFrame(win, fg_color=CARD_BG,
                                corner_radius=0, height=50)
        btn_row.pack(fill="x", side="bottom")
        btn_row.pack_propagate(False)
        ctk.CTkButton(
            btn_row, text="🗑  Delete", fg_color="#3D1515",
            hover_color="#7F1D1D", height=34, corner_radius=6,
            font=ctk.CTkFont(size=12),
            command=lambda: self._do_delete(rid, win)).pack(
            side="left", padx=12, pady=8)
        ctk.CTkButton(
            btn_row, text="✏️  Edit", fg_color=ACCENT2,
            hover_color="#1E40AF", height=34, corner_radius=6,
            font=ctk.CTkFont(size=12),
            command=lambda: self._open_edit(rid, win)).pack(
            side="left", padx=4, pady=8)
        ctk.CTkButton(
            btn_row, text="Close", fg_color=BORDER,
            height=34, font=ctk.CTkFont(size=12), corner_radius=6,
            command=win.destroy).pack(side="right", padx=12, pady=8)

    def _open_edit(self, rid, win):
        """Close the read-only detail popup and open the Edit form page."""
        win.destroy()
        self.show_page_with_arg("add", edit_id=rid)

    def _do_delete(self, rid, win):
        if messagebox.askyesno(
                "Delete Risk",
                "Permanently delete this risk?\nThis cannot be undone."):
            delete_risk(rid)
            win.destroy()
            self._refresh_statusbar()
            self.show_page("register")
            self._toast("🗑  Risk deleted", color=ORANGE)

    # ── Add Risk Manually ─────────────────────────────────────────────────────
    def _pg_add_manual(self):
        edit_id = getattr(self, "_pending_edit_id", None)
        self._pending_edit_id = None  # consume once so re-entering via
                                       # sidebar nav always opens a blank Add form
        self._pg_risk_form(edit_id=edit_id)

    def _pg_edit_risk(self, rid):
        self._pg_risk_form(edit_id=rid)

    def _pg_risk_form(self, edit_id=None):
        """
        Shared form for both Add Risk and Edit Risk. When edit_id is set,
        the form is pre-filled from the existing row and the submit button
        calls update_risk() instead of insert_risk().
        """
        existing = get_risk(edit_id) if edit_id else None
        title_text = "✏️  Edit Risk" if edit_id else "➕  Add Risk Manually"
        sub_text = (f"Editing Risk #{edit_id} · NIST SP 800-30 scoring"
                    if edit_id else
                    "Framework-aligned · NIST SP 800-30 scoring")
        self._hdr(title_text, sub_text)

        def g(key, fallback=""):
            """Pull a prefill value from the existing row, if editing."""
            if existing is None:
                return fallback
            val = existing[key] if key in existing.keys() else None
            return val if val not in (None, "") else fallback

        scroll = ctk.CTkScrollableFrame(self.main, fg_color=DARK_BG)
        scroll.pack(fill="both", expand=True)
        self._fv = {}

        def sec(title):
            ctk.CTkLabel(scroll, text=title,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=ACCENT2).pack(
                         anchor="w", padx=20, pady=(12, 3))
            f = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
            f.pack(fill="x", padx=16, pady=(0, 4))
            f.grid_columnconfigure(1, weight=1)
            return f

        def fld(frm, r, label, key,
                default="", wtype="entry", vals=None, req=False):
            ctk.CTkLabel(
                frm, text=label + (" *" if req else ""),
                font=ctk.CTkFont(size=11),
                text_color=TEXT_MAIN if req else TEXT_MUTED,
                width=170, anchor="w").grid(
                row=r, column=0, padx=(14, 6), pady=7, sticky="w")

            if wtype == "slider":
                var = ctk.DoubleVar(
                    value=float(default) if default != "" else 3.0)
                sf = ctk.CTkFrame(frm, fg_color="transparent")
                sf.grid(row=r, column=1,
                        padx=(0, 14), pady=7, sticky="ew")
                sf.grid_columnconfigure(0, weight=1)
                sl = ctk.CTkSlider(sf, from_=1, to=5,
                                   number_of_steps=4, variable=var)
                sl.grid(row=0, column=0,
                        sticky="ew", padx=(0, 6))
                lbl_map = (LIKELIHOOD_LBL if "like" in key
                           else IMPACT_LBL)
                lv = ctk.CTkLabel(sf, text="",
                                   font=ctk.CTkFont(size=11),
                                   text_color=ACCENT, width=120)
                lv.grid(row=0, column=1)

                def upd(*a, lv=lv, var=var, m=lbl_map):
                    try:
                        iv = int(round(var.get()))
                        lv.configure(text=f"{iv} — {m.get(iv,'')}")
                    except Exception:
                        pass
                var.trace_add("write", upd)
                upd()
                self._fv[key] = var
                return

            elif wtype == "text":
                w = ctk.CTkTextbox(frm, height=60,
                                    font=ctk.CTkFont(size=11),
                                    fg_color=BORDER)
                if default:
                    w.insert("1.0", str(default))
                self._fv[key] = w
                w.grid(row=r, column=1,
                       padx=(0, 14), pady=7, sticky="ew")
                return

            else:
                var = ctk.StringVar(value=str(default))
                if wtype == "option":
                    w = ctk.CTkOptionMenu(
                        frm, variable=var,
                        values=vals or [],
                        fg_color=BORDER, button_color=ACCENT2,
                        font=ctk.CTkFont(size=11))
                else:
                    w = ctk.CTkEntry(frm, textvariable=var,
                                      font=ctk.CTkFont(size=11))
                w.grid(row=r, column=1,
                       padx=(0, 14), pady=7, sticky="ew")
                self._fv[key] = var

        # ── Section 1 ─────────────────────────────────────────────────────
        f1 = sec("1  Core Details")
        fld(f1, 0, "Title",           "title",  g("title"),  req=True)
        fld(f1, 1, "Description",     "description",
            g("description"), wtype="text")
        fld(f1, 2, "Category",        "category",
            g("category", "Technical"), wtype="option", vals=CATEGORIES)
        fld(f1, 3, "Owner",           "owner",  g("owner"),  req=True)
        fld(f1, 4, "Status",          "status",
            g("status", "Open"), wtype="option", vals=RISK_STATUS)
        fld(f1, 5, "Date Identified", "date_identified",
            g("date_identified", today()))
        fld(f1, 6, "Review Date",     "review_date",
            g("review_date", ""))
        fld(f1, 7, "Priority",        "priority",
            g("priority", "Short-term"), wtype="option",
            vals=["Immediate","Short-term","Medium-term","Long-term"])

        # ── Section 2 ─────────────────────────────────────────────────────
        f2 = sec("2  Risk Scoring — NIST SP 800-30")
        fld(f2, 0, "Likelihood (1–5)", "likelihood",
            float(g("likelihood", 3) or 3), wtype="slider")
        fld(f2, 1, "Impact (1–5)",     "impact",
            float(g("impact", 3) or 3), wtype="slider")
        fld(f2, 2, "Residual Score",   "residual_score",
            str(g("residual_score", 6)))

        sc_lbl = ctk.CTkLabel(f2, text="Inherent Score: 9 — MEDIUM",
                               font=ctk.CTkFont(size=12, weight="bold"),
                               text_color=GOLD)
        sc_lbl.grid(row=3, column=0, columnspan=2,
                    padx=14, pady=(2, 10))

        def upd_sc(*a):
            try:
                l = int(round(self._fv["likelihood"].get()))
                i = int(round(self._fv["impact"].get()))
                s = l * i
                sc_lbl.configure(
                    text=f"Inherent Score: {s} — {score_label(s)}",
                    text_color=score_color(s))
            except Exception:
                pass

        self._fv["likelihood"].trace_add("write", upd_sc)
        self._fv["impact"].trace_add("write", upd_sc)
        upd_sc()

        # ── Section 3 ─────────────────────────────────────────────────────
        f3 = sec("3  NIST CSF Mapping")
        start_fn = g("nist_function", NIST_FUNCTIONS[0])
        fld(f3, 0, "NIST Function", "nist_function",
            start_fn, wtype="option", vals=NIST_FUNCTIONS)

        start_cats = NIST_CATEGORIES.get(start_fn, NIST_CATEGORIES[NIST_FUNCTIONS[0]])
        start_cat = g("nist_category", start_cats[0])
        if start_cat not in start_cats:
            start_cats = start_cats + [start_cat]
        nist_cat_var = ctk.StringVar(value=start_cat)
        ctk.CTkLabel(f3, text="NIST Category",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED,
                     width=170, anchor="w").grid(
                     row=1, column=0, padx=(14, 6), pady=7, sticky="w")
        self._nist_cat_m = ctk.CTkOptionMenu(
            f3, variable=nist_cat_var,
            values=start_cats,
            fg_color=BORDER, button_color=ACCENT2,
            font=ctk.CTkFont(size=11))
        self._nist_cat_m.grid(row=1, column=1,
                               padx=(0, 14), pady=7, sticky="ew")
        self._fv["nist_category"] = nist_cat_var

        def on_fn(*a):
            v = self._fv.get("nist_function")
            if v is None:
                return
            cats = NIST_CATEGORIES.get(v.get(), [])
            if cats:
                self._nist_cat_m.configure(values=cats)
                nist_cat_var.set(cats[0])

        if "nist_function" in self._fv:
            self._fv["nist_function"].trace_add("write", on_fn)

        fld(f3, 2, "NIST Subcategory", "nist_subcategory",
            g("nist_subcategory", "e.g. PR.AC-1"))

        # ── Section 4 ─────────────────────────────────────────────────────
        f4 = sec("4  ISO 27001:2022 | CIA | MITRE ATT&CK | CIS")
        # Compatibility: existing risks may have legacy ISO 27001:2013
        # domain values (e.g. "A.9 Access Control"). If the saved value
        # is not in the current 2022 list, append it so it stays visible
        # in the dropdown and is not silently replaced when the form loads.
        saved_iso = g("iso_domain", ISO_DOMAINS[0])
        iso_vals = (ISO_DOMAINS if saved_iso in ISO_DOMAINS
                    else ISO_DOMAINS + [saved_iso + " (legacy)"])
        fld(f4, 0, "ISO 27001 Domain",     "iso_domain",
            saved_iso, wtype="option", vals=iso_vals)
        fld(f4, 1, "ISO Control Ref",      "iso_control",
            g("iso_control", "e.g. A.9.4.1"))
        fld(f4, 2, "CIA Component",        "cia_component",
            g("cia_component", CIA_COMPONENTS[0]),
            wtype="option", vals=CIA_COMPONENTS)
        fld(f4, 3, "MITRE ATT&CK Tactic", "mitre_tactic",
            g("mitre_tactic", MITRE_TACTICS[-1]),
            wtype="option", vals=MITRE_TACTICS)
        fld(f4, 4, "MITRE Technique",      "mitre_technique",
            g("mitre_technique", "e.g. T1078 Valid Accounts"))
        fld(f4, 5, "CIS Control",          "cis_control",
            g("cis_control", CIS_CONTROLS[-1]),
            wtype="option", vals=CIS_CONTROLS)

        # ── Section 5 ─────────────────────────────────────────────────────
        f5 = sec("5  Mitigation & Notes")
        fld(f5, 0, "Existing Controls", "existing_controls",
            g("existing_controls"), wtype="text")
        fld(f5, 1, "Mitigation Plan",   "mitigation",
            g("mitigation"), wtype="text")
        fld(f5, 2, "Notes",             "notes",
            g("notes"), wtype="text")

        # ── Submit ─────────────────────────────────────────────────────────
        self._add_status = ctk.CTkLabel(scroll, text="",
                                         font=ctk.CTkFont(size=11))
        self._add_status.pack(pady=4)

        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(2, 20))
        if edit_id:
            ctk.CTkButton(btn_row, text="💾  Save Changes",
                          height=44, fg_color=ACCENT2,
                          font=ctk.CTkFont(size=13), corner_radius=8,
                          command=lambda: self._submit_risk_form(edit_id)
                          ).pack(side="left", fill="x", expand=True,
                                 padx=(0, 6))
            ctk.CTkButton(btn_row, text="Cancel",
                          height=44, fg_color=BORDER,
                          hover_color="#2D3748",
                          font=ctk.CTkFont(size=13), corner_radius=8,
                          command=lambda: self._view_risk(edit_id)
                          ).pack(side="left", padx=(6, 0))
        else:
            ctk.CTkButton(scroll.master if False else btn_row,
                          text="➕  Add to Risk Register",
                          height=44, fg_color=ACCENT,
                          font=ctk.CTkFont(size=13), corner_radius=8,
                          command=lambda: self._submit_risk_form(None)
                          ).pack(fill="x", expand=True)

    def _submit_risk_form(self, edit_id=None):
        def gv(k):
            v = self._fv.get(k)
            if v is None:
                return ""
            if isinstance(v, ctk.CTkTextbox):
                return v.get("1.0", "end").strip()
            if isinstance(v, ctk.DoubleVar):
                return v.get()
            return v.get()

        title = str(gv("title")).strip()
        owner = str(gv("owner")).strip()

        if not title:
            self._add_status.configure(
                text="⚠ Title is required", text_color=RED)
            return
        if not owner:
            self._add_status.configure(
                text="⚠ Owner is required", text_color=RED)
            return

        try:
            lik = max(1, min(5, int(round(float(gv("likelihood"))))))
        except Exception:
            lik = 3
        try:
            imp = max(1, min(5, int(round(float(gv("impact"))))))
        except Exception:
            imp = 3

        res_raw = str(gv("residual_score")).strip()
        try:
            res = max(1, int(float(res_raw))) if res_raw else max(1, lik*imp-2)
        except Exception:
            res = max(1, lik * imp - 2)

        rev = str(gv("review_date")).strip()
        did = str(gv("date_identified")).strip()
        if rev and not validate_date(rev):
            self._add_status.configure(
                text="⚠ Review date must be YYYY-MM-DD", text_color=RED)
            return
        if did and not validate_date(did):
            self._add_status.configure(
                text="⚠ Identified date must be YYYY-MM-DD", text_color=RED)
            return

        # Build data dict — only string/numeric values, not widget objects
        data = {}
        skip_keys = {"likelihood", "impact", "residual_score"}
        for k in self._fv:
            if k not in skip_keys:
                data[k] = gv(k)

        data.update({
            "title":            title,
            "owner":            owner,
            "likelihood":       lik,
            "impact":           imp,
            "residual_score":   res,
            "date_identified":  did or today(),
        })

        try:
            if edit_id:
                update_risk(edit_id, data)
            else:
                rid = insert_risk(data, source="Manual")
        except Exception as e:
            self._add_status.configure(
                text=f"⚠ DB error: {e}", text_color=RED)
            return

        score = lik * imp
        if edit_id:
            self._add_status.configure(
                text=f"✅ Risk #{edit_id} updated — "
                     f"Score: {score} ({score_label(score)})",
                text_color=GREEN)
            self.after(1200, lambda: self._after_edit_risk(edit_id, score))
        else:
            self._add_status.configure(
                text=f"✅ Risk #{rid} saved — "
                     f"Score: {score} ({score_label(score)})",
                text_color=GREEN)
            self.after(1200, lambda: self._after_add_risk(rid, score))

    def _after_edit_risk(self, rid, score):
        """Navigate back to the risk's detail view after a successful edit,
        with a toast. Dashboard/Matrix/Register/Export all read live from
        the DB on every render, so no separate refresh call is needed
        beyond the status bar and re-navigating."""
        self._refresh_statusbar()
        self._view_risk(rid)
        self._toast(
            f"✅  Risk #{rid} updated — Score: {score} ({score_label(score)})")

    def _after_add_risk(self, rid, score):
        """Navigate to register after successful add, with toast."""
        self._refresh_statusbar()
        self.show_page("register")
        self._toast(
            f"✅  Risk #{rid} added — Score: {score} ({score_label(score)})")

    # ── Risk Matrix ───────────────────────────────────────────────────────────
    def _pg_matrix(self):
        self._hdr("🎯  Risk Matrix",
                  "5×5 heatmap · NIST SP 800-30 · click a cell to see risks",
                  refresh_cmd=lambda: self.show_page("matrix"))
        info = ctk.CTkFrame(self.main, fg_color=CARD_BG, corner_radius=8)
        info.pack(fill="x", padx=18, pady=(4, 10))
        for lbl, color in [
            ("■ LOW 1–4", GREEN), ("■ MEDIUM 5–9", GOLD),
            ("■ HIGH 10–14", ORANGE), ("■ CRITICAL 15–25", RED),
        ]:
            ctk.CTkLabel(info, text=lbl, font=ctk.CTkFont(size=11),
                         text_color=color).pack(
                         side="left", padx=12, pady=8)

        mf = ctk.CTkFrame(self.main, fg_color=DARK_BG)
        mf.pack(padx=18, pady=0)
        ctk.CTkLabel(mf, text="IMPACT →",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=TEXT_MUTED).grid(
                     row=0, column=2, columnspan=5, pady=(0, 3))
        IMP_LBL2 = {1:"Negligible",2:"Minor",3:"Moderate",
                    4:"Major",5:"Critical"}
        LIK_LBL2 = {1:"Rare",2:"Unlikely",3:"Possible",
                    4:"Likely",5:"Almost Certain"}
        for ci, imp in enumerate(range(1, 6)):
            ctk.CTkLabel(mf, text=f"{IMP_LBL2[imp]}\n({imp})",
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED,
                         width=95, justify="center").grid(
                         row=1, column=ci+2, padx=2)
        ctk.CTkLabel(mf, text="L\nI\nK\nE\nL\nI\nH\nO\nO\nD",
                     font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=TEXT_MUTED).grid(
                     row=2, column=0, rowspan=5, padx=(0, 4))
        with get_db() as conn:
            for ri, lik in enumerate(range(5, 0, -1)):
                ctk.CTkLabel(mf, text=f"{LIK_LBL2[lik]}\n({lik})",
                             font=ctk.CTkFont(size=9),
                             text_color=TEXT_MUTED,
                             width=85, justify="right").grid(
                             row=ri+2, column=1,
                             padx=(0, 4), pady=2)
                for ci, imp in enumerate(range(1, 6)):
                    sc  = lik * imp
                    cnt = conn.execute(
                        "SELECT COUNT(*) FROM risks "
                        "WHERE likelihood=? AND impact=?",
                        (lik, imp)).fetchone()[0]
                    col = score_color(sc)
                    ctk.CTkButton(
                        mf,
                        text=f"{sc}\n({cnt})" if cnt else str(sc),
                        font=ctk.CTkFont(size=11, weight="bold"),
                        width=95, height=58, corner_radius=6,
                        fg_color=col, hover_color=col,
                        text_color="white",
                        command=lambda l=lik, i=imp, s=sc, c=cnt:
                            self._matrix_click(l, i, s, c)).grid(
                        row=ri+2, column=ci+2, padx=2, pady=2)
        ctk.CTkLabel(self.main,
                     text="Score = Likelihood × Impact  ·  "
                          "(n) = risks logged at this cell",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(pady=6)

    def _matrix_click(self, lik, imp, score, count):
        if count == 0:
            messagebox.showinfo("Risk Matrix",
                                f"Score {score}: No risks logged here.")
            return
        # Pull full rows (not just title/owner/status/source) so each
        # entry in this list has everything _view_risk needs if clicked.
        with get_db() as conn:
            risks = conn.execute(
                "SELECT * FROM risks WHERE likelihood=? AND impact=?",
                (lik, imp)).fetchall()
        win = ctk.CTkToplevel(self)
        win.title(f"Score {score} — {count} risk(s)")
        win.geometry("640x420")
        win.configure(fg_color=DARK_BG)
        win.grab_set()
        set_icon(win)
        ctk.CTkLabel(win, text=f"{count} risk(s) at score {score}",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=score_color(score)).pack(
                     padx=18, pady=14, anchor="w")
        ctk.CTkLabel(win, text="Click a risk to view full details",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).pack(
                     padx=18, pady=(0, 8), anchor="w")
        sf = ctk.CTkScrollableFrame(win, fg_color=CARD_BG,
                                     corner_radius=10)
        sf.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        # BUG FIX: this popup previously called rf.grid_propagate(False)
        # without ever giving rf an explicit width — identical to the
        # Risk Register bug fixed earlier. With auto-sizing disabled and
        # no width set, each row frame collapsed to ~0px, clipping every
        # label inside it. This popup also only ever SELECTed and showed
        # title/status — not the full risk. Both are fixed below: rows
        # size naturally (no grid_propagate), and clicking opens the
        # same full _view_risk window used everywhere else in the app,
        # so Register, Matrix, and any future entry points all show
        # identical, complete risk details rather than three different
        # partial views drifting out of sync.
        sf.grid_columnconfigure(0, weight=1)
        for i, r in enumerate(risks):
            bg = CARD_BG if i % 2 == 0 else "#1E2436"
            rf = ctk.CTkFrame(sf, fg_color=bg, corner_radius=6)
            rf.grid(row=i, column=0, sticky="ew", padx=4, pady=2)
            rf.grid_columnconfigure(0, weight=1)
            click = lambda e, rid=r["id"]: (win.destroy(),
                                            self._view_risk(rid))
            sc_r = int(r["risk_score"] or 0)
            score_lbl = ctk.CTkLabel(
                rf, text=f"{score_label(sc_r)}",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=score_color(sc_r), width=70, anchor="w")
            score_lbl.grid(row=0, column=0, padx=(10, 4), pady=8, sticky="w")
            title_lbl = ctk.CTkLabel(
                rf, text=r["title"] or "(untitled)",
                font=ctk.CTkFont(size=12), text_color=TEXT_MAIN,
                anchor="w")
            title_lbl.grid(row=0, column=1, padx=4, pady=8, sticky="w")
            rf.grid_columnconfigure(1, weight=1)
            status_lbl = ctk.CTkLabel(
                rf, text=r["status"] or "—",
                font=ctk.CTkFont(size=10),
                text_color=(GOLD if r["status"] == "Open" else GREEN))
            status_lbl.grid(row=0, column=2, padx=8, pady=8)
            owner_lbl = ctk.CTkLabel(
                rf, text=r["owner"] or "Unassigned",
                font=ctk.CTkFont(size=10), text_color=TEXT_MUTED)
            owner_lbl.grid(row=0, column=3, padx=(4, 10), pady=8)
            for w in (rf, score_lbl, title_lbl, status_lbl, owner_lbl):
                w.bind("<Button-1>", click)
                w.configure(cursor="hand2")

    # ── Export & Report ───────────────────────────────────────────────────────
    def _update_last_backup_label(self):
        """Scan the backups folder for the most recent backup file and
        update the label showing its timestamp. Pure read of the
        filesystem — does not touch the database."""
        if not hasattr(self, "_last_backup_lbl"):
            return
        backups_dir = BASE_DIR / "backups"
        try:
            files = sorted(backups_dir.glob("riskcore_backup_*.db"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            files = []
        if files:
            mtime = datetime.datetime.fromtimestamp(files[0].stat().st_mtime)
            self._last_backup_lbl.configure(
                text=f"Last backup:  "
                     f"{mtime.strftime('%Y-%m-%d %H:%M:%S')}  "
                     f"({files[0].name})")
        else:
            self._last_backup_lbl.configure(
                text="Last backup:  none yet")

    def _pg_export(self):
        self._hdr("📤  Export & Report",
                  "Industry-standard GRC report · NIST SP 800-30 aligned")
        risks = get_risks()
        cnt   = len(risks)

        info = ctk.CTkFrame(self.main, fg_color=CARD_BG, corner_radius=10)
        info.pack(fill="x", padx=18, pady=(6, 12))
        info.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(info,
                     text=f"Register contains {cnt} risk(s)",
                     font=ctk.CTkFont(size=13),
                     text_color=TEXT_MAIN).grid(
                     row=0, column=0, padx=16, pady=12, sticky="w")
        ctk.CTkLabel(info, text="Company Name:",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=0, column=1, padx=8, pady=12, sticky="e")
        self._exp_cn_var = ctk.StringVar(value=self._company_name)
        ctk.CTkEntry(info, textvariable=self._exp_cn_var,
                     width=220, font=ctk.CTkFont(size=11)).grid(
                     row=0, column=2, padx=(0, 14), pady=12)
        ctk.CTkLabel(info, text="Classification:",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, padx=16, pady=(0, 12), sticky="w")
        self._exp_clf_var = ctk.StringVar(
            value=self._settings.get("default_classification", "CONFIDENTIAL"))
        ctk.CTkOptionMenu(info, variable=self._exp_clf_var,
                          values=["CONFIDENTIAL","RESTRICTED",
                                  "INTERNAL","PUBLIC"],
                          fg_color=BORDER, button_color=ACCENT,
                          font=ctk.CTkFont(size=11), width=160).grid(
                          row=1, column=1, padx=8, pady=(0, 12), sticky="w")

        self._exp_status = ctk.CTkLabel(
            self.main, text="", font=ctk.CTkFont(size=11))
        self._exp_status.pack(pady=2)

        btn_frame = ctk.CTkFrame(self.main, fg_color="transparent")
        btn_frame.pack(fill="x", padx=18, pady=4)

        def export_pdf_report():
            company = self._exp_cn_var.get().strip() or "Your Organisation"
            clf     = self._exp_clf_var.get()
            analysis = getattr(self, "_last_analysis", None)
            risk_rows = get_risks()
            risks_approved = [dict(r) for r in risk_rows]
            for r in risks_approved:
                if not r.get("inherent_score"):
                    r["inherent_score"] = int(r.get("risk_score") or 0)
                if not r.get("residual_score"):
                    r["residual_score"] = max(1, r["inherent_score"] - 2)
            if not risks_approved:
                messagebox.showinfo(
                    "No Risks",
                    "Add risks to the register before exporting.")
                return
            if not analysis:
                from riskcore_ai import build_data_driven_analysis
                analysis = build_data_driven_analysis(
                    risks_approved, company)
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile=(f"RiskCore_GRC_Report_"
                             f"{company.replace(' ','_')}_{today()}.pdf"))
            if not path:
                return
            self._exp_status.configure(
                text="⏳ Generating PDF report...", text_color=GOLD)
            self.update()
            try:
                from riskcore_ai import generate_pdf_report
                generate_pdf_report(
                    analysis, risks_approved, company, path, clf)
                self._exp_status.configure(
                    text=f"✅ Report saved: {Path(path).name}",
                    text_color=GREEN)
                audit("EXPORT_PDF",
                      detail=f"{cnt} risks → {Path(path).name}")
                self._toast(f"✅  PDF Export Successful — {Path(path).name}")
            except Exception as e:
                self._exp_status.configure(
                    text=f"⚠ Error: {e}", text_color=RED)

        def export_csv():
            if not risks:
                messagebox.showinfo("Export", "No risks to export.")
                return
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile=f"RiskCore_Export_{today()}.csv")
            if not path:
                return
            cols = [
                "id","title","description","category",
                "nist_function","nist_category","iso_domain",
                "cia_component","mitre_tactic","cis_control",
                "likelihood","impact","risk_score",
                "inherent_score","residual_score",
                "owner","status","mitigation","review_date",
                "date_identified","source","confidence","priority",
            ]
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols,
                                   extrasaction="ignore")
                w.writeheader()
                for r in risks:
                    w.writerow({c: r[c] for c in cols
                                if c in r.keys()})
            audit("EXPORT_CSV",
                  detail=f"{cnt} risks → {Path(path).name}")
            self._exp_status.configure(
                text=f"✅ CSV exported: {Path(path).name}",
                text_color=GREEN)
            self._toast(f"✅  CSV Export Successful — {Path(path).name}")

        def export_db_backup():
            try:
                dest = backup_database()
                self._exp_status.configure(
                    text=f"✅ Database backed up: {dest.name}",
                    text_color=GREEN)
                self._toast(f"✅  Database Backup Successful — {dest.name}")
                self._refresh_statusbar()
                self._update_last_backup_label()
            except Exception as e:
                self._exp_status.configure(
                    text=f"⚠ Backup error: {e}", text_color=RED)

        ctk.CTkButton(
            btn_frame, text="📄  Full GRC PDF Report",
            height=48, width=220,
            fg_color=ACCENT,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=export_pdf_report).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btn_frame, text="📊  Export CSV",
            height=48, width=180,
            fg_color=GREEN, font=ctk.CTkFont(size=13),
            corner_radius=8,
            command=export_csv).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btn_frame, text="💾  Backup Database",
            height=48, width=180,
            fg_color=ACCENT2, font=ctk.CTkFont(size=13),
            corner_radius=8,
            command=export_db_backup).pack(side="left")

        backup_note = ctk.CTkFrame(self.main, fg_color=CARD_BG,
                                   corner_radius=8)
        backup_note.pack(fill="x", padx=18, pady=(10, 0))
        ctk.CTkLabel(
            backup_note, text="💾  Database Backup",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MAIN).pack(padx=14, pady=(10, 2), anchor="w")
        ctk.CTkLabel(
            backup_note,
            text=f"Backup folder:  {BASE_DIR / 'backups'}",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
            justify="left").pack(padx=14, pady=(2, 1), anchor="w")
        self._last_backup_lbl = ctk.CTkLabel(
            backup_note, text="Last backup:  checking…",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
            justify="left")
        self._last_backup_lbl.pack(padx=14, pady=(1, 2), anchor="w")
        ctk.CTkLabel(
            backup_note,
            text="Each backup is a complete timestamped copy of "
                 "riskcore.db. No schema changes are made.",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
            justify="left", wraplength=820).pack(
            padx=14, pady=(1, 10), anchor="w")
        self._update_last_backup_label()

        note = ctk.CTkFrame(self.main, fg_color="#1C2820",
                             corner_radius=8)
        note.pack(fill="x", padx=18, pady=(10, 0))
        ctk.CTkLabel(
            note,
            text="📋  PDF Report: Cover · ToC · Executive Summary · "
                 "Risk Register · Detailed Profiles · NIST CSF Maturity "
                 "· Framework Gap Analysis · Remediation Roadmap "
                 "· Methodology Appendix · Framework References\n"
                 "Classification banner on every page  ·  "
                 "NIST SP 800-30  ·  ISO/IEC 27001:2022 A.8 Technological Controls",
            font=ctk.CTkFont(size=10), text_color=GREEN,
            justify="left", wraplength=820).pack(
            padx=14, pady=10, anchor="w")

    # ── Audit Log ─────────────────────────────────────────────────────────────
    def _pg_audit(self):
        self._hdr("🔍  Audit Log",
                  "Immutable record · ISO/IEC 27001:2022 A.8 compliant",
                  refresh_cmd=lambda: self.show_page("audit"))
        with get_db() as conn:
            logs = conn.execute(
                "SELECT * FROM audit_log "
                "ORDER BY id DESC LIMIT 300").fetchall()

        total_lbl = ctk.CTkLabel(
            self.main,
            text=f"{len(logs)} most recent entries",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED)
        total_lbl.pack(anchor="e", padx=20, pady=(0, 4))

        scroll = ctk.CTkScrollableFrame(
            self.main, fg_color=CARD_BG, corner_radius=10)
        scroll.pack(fill="both", expand=True,
                    padx=18, pady=(0, 18))
        scroll.grid_columnconfigure(3, weight=1)

        for col, h in enumerate(["Timestamp","Action",
                                  "Risk ID","Detail"]):
            ctk.CTkLabel(scroll, text=h,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=TEXT_MUTED).grid(
                         row=0, column=col,
                         padx=8, pady=(8, 4), sticky="w")

        colors_map = {
            "CREATE":      GREEN,
            "UPDATE":      ACCENT2,
            "DELETE":      RED,
            "EXPORT_PDF":  PURPLE,
            "EXPORT_CSV":  GOLD,
            "AI_ANALYSIS": PURPLE,
            "AI_APPROVE":  GREEN,
            "APP_START":   TEXT_MUTED,
        }
        for i, log in enumerate(logs, 1):
            c = colors_map.get(log["action"], TEXT_MUTED)
            ctk.CTkLabel(scroll,
                         text=(log["timestamp"] or "")[:19],
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).grid(
                         row=i, column=0, padx=8, pady=2, sticky="w")
            ctk.CTkLabel(scroll, text=log["action"],
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=c).grid(
                         row=i, column=1, padx=8, pady=2)
            ctk.CTkLabel(scroll,
                         text=str(log["risk_id"] or "—"),
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).grid(
                         row=i, column=2, padx=8, pady=2)
            ctk.CTkLabel(scroll, text=log["detail"] or "—",
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=i, column=3, padx=8, pady=2, sticky="w")

    # ── Settings ──────────────────────────────────────────────────────────────
    def _pg_settings(self):
        self._hdr("⚙️  Settings",
                  "Organisation details, AI configuration, and app information")
        scroll = ctk.CTkScrollableFrame(self.main, fg_color=DARK_BG)
        scroll.pack(fill="both", expand=True)

        # ── Organisation Settings ────────────────────────────────────────────
        org_f = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        org_f.pack(fill="x", padx=18, pady=(8, 8))
        org_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(org_f, text="🏢  Organisation Settings",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).grid(
                     row=0, column=0, columnspan=2,
                     padx=14, pady=(12, 8), sticky="w")

        ctk.CTkLabel(org_f, text="Organisation Name",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, padx=14, pady=8, sticky="w")
        self._set_org_var = ctk.StringVar(
            value=self._settings.get("organisation_name", "Your Organisation"))
        ctk.CTkEntry(org_f, textvariable=self._set_org_var,
                     font=ctk.CTkFont(size=12)).grid(
                     row=1, column=1, padx=14, pady=8, sticky="ew")

        ctk.CTkLabel(org_f, text="Default Report Classification",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=2, column=0, padx=14, pady=(8, 14), sticky="w")
        self._set_clf_var = ctk.StringVar(
            value=self._settings.get("default_classification", "CONFIDENTIAL"))
        ctk.CTkOptionMenu(org_f, variable=self._set_clf_var,
                          values=["PUBLIC", "INTERNAL",
                                  "CONFIDENTIAL", "RESTRICTED"],
                          fg_color=BORDER, button_color=ACCENT2,
                          font=ctk.CTkFont(size=11)).grid(
                          row=2, column=1, padx=14, pady=(8, 14), sticky="w")

        # ── AI Settings ───────────────────────────────────────────────────────
        ai_f = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        ai_f.pack(fill="x", padx=18, pady=(0, 8))
        ai_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ai_f, text="🤖  AI Settings",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).grid(
                     row=0, column=0, columnspan=3,
                     padx=14, pady=(12, 8), sticky="w")

        ctk.CTkLabel(ai_f, text="Claude API Key",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, padx=14, pady=8, sticky="w")
        self._set_key_var = ctk.StringVar(value=self._api_key)
        ctk.CTkEntry(ai_f, textvariable=self._set_key_var,
                     show="•", font=ctk.CTkFont(size=12),
                     placeholder_text="sk-ant-api03-...").grid(
                     row=1, column=1, padx=(0, 8), pady=8, sticky="ew")

        test_status = ctk.CTkLabel(ai_f, text="", font=ctk.CTkFont(size=10))
        test_status.grid(row=2, column=0, columnspan=3,
                         padx=14, pady=(0, 4), sticky="w")

        enc_status_text = ("🔒  Encrypted at rest (Fernet)" if self._api_key
                           else "⚠ No API key saved yet")
        enc_status_color = GREEN if self._api_key else GOLD
        enc_status = ctk.CTkLabel(ai_f, text=enc_status_text,
                                  font=ctk.CTkFont(size=10),
                                  text_color=enc_status_color)
        enc_status.grid(row=3, column=0, columnspan=3,
                        padx=14, pady=(0, 12), sticky="w")

        def test_connection():
            key = self._set_key_var.get().strip()
            if not key.startswith("sk-ant"):
                test_status.configure(
                    text="⚠ Key should start with 'sk-ant-api03-'",
                    text_color=RED)
                return
            test_status.configure(text="⏳ Testing connection...",
                                  text_color=GOLD)
            self.update()

            def run():
                import urllib.request, urllib.error
                try:
                    payload = json.dumps({
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 16,
                        "messages": [{"role": "user", "content": "Reply with OK"}]
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        "https://api.anthropic.com/v1/messages",
                        data=payload,
                        headers={
                            "Content-Type":      "application/json",
                            "x-api-key":         key,
                            "anthropic-version": "2023-06-01",
                        },
                        method="POST")
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        resp.read()
                    def ok():
                        test_status.configure(
                            text="✅ Connection successful — API key is valid",
                            text_color=GREEN)
                    self.after(0, ok)
                except urllib.error.HTTPError as e:
                    def fail(code=e.code):
                        msg = ("Invalid API key" if code in (401, 403)
                              else f"Server responded with error {code}")
                        test_status.configure(text=f"⚠ {msg}", text_color=RED)
                    self.after(0, fail)
                except Exception as e:
                    def fail2(msg=str(e)):
                        test_status.configure(
                            text=f"⚠ Connection failed: {msg}",
                            text_color=RED)
                    self.after(0, fail2)

            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(ai_f, text="Test Connection", width=140, height=30,
                      fg_color=PURPLE, font=ctk.CTkFont(size=11),
                      corner_radius=6,
                      command=test_connection).grid(
                      row=1, column=2, padx=(0, 14), pady=8)

        # ── Application Information ──────────────────────────────────────────
        info_f = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        info_f.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(info_f, text="ℹ️  Application Information",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).pack(
                     padx=14, pady=(12, 8), anchor="w")
        for line in [
            "RiskCore GRC Platform — Version 1.0",
            "Build: Stable Release",
            "Frameworks Supported: NIST CSF 2.0 · ISO 27001:2022 · "
            "MITRE ATT&CK · CIS Controls v8 · CIA Triad",
            "Scoring Methodology: NIST SP 800-30 Rev 1",
            "Database: SQLite (local, encrypted API key at rest)",
            "Developer: Michael Waugh",
        ]:
            ctk.CTkLabel(info_f, text=line, font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).pack(
                         padx=14, pady=2, anchor="w")

        last_saved_val = self._settings.get("last_saved", "")
        last_saved_text = (f"Settings last saved: {last_saved_val}"
                           if last_saved_val
                           else "Settings last saved: never")
        self._last_saved_lbl = ctk.CTkLabel(
            info_f, text=last_saved_text,
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED)
        self._last_saved_lbl.pack(padx=14, pady=(8, 12), anchor="w")

        # ── Save ──────────────────────────────────────────────────────────────
        self._settings_status = ctk.CTkLabel(
            scroll, text="", font=ctk.CTkFont(size=11))
        self._settings_status.pack(pady=4)

        def save_all_settings():
            org_name = self._set_org_var.get().strip() or "Your Organisation"
            clf = self._set_clf_var.get()
            key = self._set_key_var.get().strip()

            self._settings = {
                "organisation_name": org_name,
                "default_classification": clf,
                "last_saved": datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"),
            }
            ok = save_settings(self._settings)
            self._company_name = org_name

            if key and key != self._api_key:
                if key.startswith("sk-ant"):
                    self._api_key = key
                    save_api_key(key)
                else:
                    self._settings_status.configure(
                        text="⚠ Settings saved, but API key was not updated "
                             "— it should start with 'sk-ant-api03-'",
                        text_color=GOLD)
                    self._toast("⚠  Settings saved (API key unchanged — "
                               "invalid format)", color=GOLD)
                    return

            if ok:
                self._settings_status.configure(
                    text="✅ Settings saved successfully", text_color=GREEN)
                self._toast("✅  Settings Saved")
                self._last_saved_lbl.configure(
                    text=f"Settings last saved: "
                         f"{self._settings['last_saved']}")
            else:
                self._settings_status.configure(
                    text="⚠ Could not write settings file", text_color=RED)

        ctk.CTkButton(scroll, text="💾  Save Settings", height=44,
                      fg_color=ACCENT, font=ctk.CTkFont(size=13),
                      corner_radius=8,
                      command=save_all_settings).pack(
                      fill="x", padx=18, pady=(2, 20))


if __name__ == "__main__":
    app = RiskCore()
    app.mainloop()
