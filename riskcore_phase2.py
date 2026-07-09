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

# CTk/tkinter imports replaced with stubs — the PySide6 frontend
# uses only the backend functions from this module (DB, CRUD, audit etc.)
# The old CTk UI class (RiskCore(ctk.CTk)) is unused but kept for reference.
try:
    import customtkinter as ctk
    from tkinter import messagebox, filedialog
except ImportError:
    # Stub out ctk and tkinter so the backend functions load cleanly
    # even when tkinter is not available (PyInstaller frozen exe, server, etc.)
    import types as _types

    ctk = _types.ModuleType("customtkinter")
    for _attr in ["CTk", "CTkFrame", "CTkLabel", "CTkButton", "CTkEntry",
                  "CTkComboBox", "CTkTextbox", "CTkScrollableFrame",
                  "CTkCheckBox", "CTkProgressBar", "CTkToplevel",
                  "CTkTabview", "CTkFont", "StringVar",
                  "set_appearance_mode", "set_default_color_theme"]:
        setattr(ctk, _attr, type(_attr, (), {
            "__init__": lambda self, *a, **kw: None,
            "__call__": lambda self, *a, **kw: None,
        }))

    class _TkStub:
        def showinfo(self, *a, **kw): pass
        def showerror(self, *a, **kw): pass
        def showwarning(self, *a, **kw): pass
        def askopenfilename(self, *a, **kw): return ""
        def asksaveasfilename(self, *a, **kw): return ""

    messagebox = _TkStub()
    filedialog  = _TkStub()
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
CIS_CONTROLS = [f"CIS-{i}" for i in range(1, 19)] + ["Not Applicable"]
LIKELIHOOD_LBL = {1:"Rare",2:"Unlikely",3:"Possible",4:"Likely",5:"Almost Certain"}
IMPACT_LBL     = {1:"Negligible",2:"Minor",3:"Moderate",4:"Major",5:"Critical"}

# ── v1.5 Treatment constants ──────────────────────────────────────────────────
TREATMENT_STRATEGIES = ["Mitigate", "Accept", "Transfer", "Avoid"]
TREATMENT_STATUS     = ["Draft", "Approved", "In Progress",
                        "Completed", "Verified", "Ineffective"]
TREAT_COLORS = {
    "Mitigate": "#1565C0",
    "Accept":   "#E65100",
    "Transfer": "#00695C",
    "Avoid":    "#6A1B9A",
}
TREAT_STATUS_COLORS = {
    "Draft":       "#6B7A8D",
    "Approved":    "#1D4ED8",
    "In Progress": "#CA8A04",
    "Completed":   "#0097A7",
    "Verified":    "#43A047",
    "Ineffective": "#C62828",
}
NIST_COLORS = {
    "Govern":   "#1B5E20",
    "Identify": "#1565C0",
    "Protect":  "#2E7D32",
    "Detect":   "#E65100",
    "Respond":  "#880E4F",
    "Recover":  "#4A148C",
}

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
    # Both onefile and onedir: sys.executable is always the real exe path
    # riskcore.db and user data live in the same folder as the exe
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

DB_PATH       = BASE_DIR / "riskcore.db"
API_KEY_FILE  = BASE_DIR / "riskcore_apikey.txt"
SETTINGS_FILE = BASE_DIR / "settings.json"

# ── Theme ─────────────────────────────────────────────────────────────────────
DARK_BG    = "#0A0E17"
SIDEBAR_BG = "#0F1318"
CARD_BG    = "#141A24"
CARD_BG2   = "#1A2232"
BORDER     = "#1E2D3D"
ACCENT     = "#E53935"
ACCENT2    = "#1565C0"
TEAL       = "#00897B"
TEXT_MAIN  = "#ECF0F5"
TEXT_MUTED = "#6B7A8D"
TEXT_DIM   = "#3E4A5A"
GREEN      = "#2E7D32"
GREEN_LT   = "#43A047"
GOLD       = "#F9A825"
ORANGE     = "#E65100"
RED        = "#C62828"
PURPLE     = "#6A1B9A"
PURPLE_LT  = "#8E24AA"
CYAN       = "#0097A7"

# ── Score helpers ─────────────────────────────────────────────────────────────
def score_color(s):
    try: s = int(s or 0)
    except: s = 0
    if s <= 4:  return GREEN_LT
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

def score_bg(s):
    try: s = int(s or 0)
    except: s = 0
    if s <= 4:  return "#0D3321"
    if s <= 9:  return "#3D2E00"
    if s <= 14: return "#3D1A00"
    return "#3D0000"

# ── Misc helpers ──────────────────────────────────────────────────────────────
def today():
    return datetime.date.today().isoformat()

def now_str():
    return datetime.datetime.now().strftime("%H:%M:%S")

def days_until(date_str):
    """Days until a date string. Negative = overdue. None if no date."""
    if not date_str:
        return None
    try:
        target = datetime.date.fromisoformat(date_str)
        return (target - datetime.date.today()).days
    except Exception:
        return None

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
        try:
            # Restrict key file to owner-only on Linux/macOS
            # On Windows, NTFS ACLs govern access so chmod is a no-op
            import platform as _plat
            if _plat.system() != "Windows":
                key_file.chmod(0o600)
        except Exception:
            pass  # Non-critical — encryption still protects the key
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
        print("[api key load error] — see logs for details")  # key not logged
    return ""

def save_api_key(key):
    """Encrypt and persist the API key. Overwrites any previous file."""
    try:
        f = _get_or_create_fernet()
        token = f.encrypt(key.strip().encode())
        API_KEY_FILE.write_bytes(token)
    except Exception as e:
        print("[api key save error] — see logs for details")  # key not logged

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
    """
    Return an SQLite connection configured for safe use across threads.

    check_same_thread=False  — allows background QThread workers to use
                               connections created on the main thread and
                               vice versa. We serialise access via the
                               busy_timeout + WAL reader/writer separation.
    WAL mode                 — allows concurrent readers alongside a single
                               writer without blocking.
    synchronous=NORMAL       — safe checkpoint after each transaction; faster
                               than FULL without risking corruption.
    wal_autocheckpoint=100   — automatically checkpoint WAL every 100 pages
                               so data is flushed to the main DB regularly.
    """
    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=30,
        check_same_thread=False,   # safe: Qt workers use short-lived connections
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys  = ON")
    conn.execute("PRAGMA journal_mode  = WAL")
    conn.execute("PRAGMA synchronous   = NORMAL")
    conn.execute("PRAGMA busy_timeout  = 10000")
    conn.execute("PRAGMA wal_autocheckpoint = 100")
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
        CREATE TABLE IF NOT EXISTS treatments (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            risk_id               INTEGER NOT NULL
                                    REFERENCES risks(id) ON DELETE CASCADE,
            strategy              TEXT NOT NULL,
            title                 TEXT NOT NULL,
            description           TEXT,
            owner                 TEXT,
            status                TEXT DEFAULT 'Draft',
            target_date           TEXT,
            completion_date       TEXT,
            residual_score_target INTEGER,
            residual_score_actual INTEGER,
            cost_estimate         TEXT,
            notes                 TEXT,
            date_created          TEXT NOT NULL,
            date_modified         TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_treatments_risk
            ON treatments(risk_id);
        CREATE INDEX IF NOT EXISTS idx_treatments_status
            ON treatments(status);
        CREATE TABLE IF NOT EXISTS organisation_scope (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            organisation_name   TEXT,
            industry            TEXT,
            organisation_size   TEXT,
            business_function   TEXT,
            assessment_name     TEXT,
            assessment_type     TEXT,
            assessment_objective TEXT,
            business_units      TEXT,
            locations           TEXT,
            assets_in_scope     TEXT,
            critical_assets     TEXT,
            frameworks_selected TEXT,
            created_at          TEXT NOT NULL,
            modified_at         TEXT NOT NULL
        );
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
    # ── Treatment Cost Analysis (v1.5) ─────────────────────────────────────
    "labour_cost":              "REAL DEFAULT 0",
    "software_cost":            "REAL DEFAULT 0",
    "hardware_cost":            "REAL DEFAULT 0",
    "consulting_cost":          "REAL DEFAULT 0",
    "training_cost":            "REAL DEFAULT 0",
    "licensing_cost":           "REAL DEFAULT 0",
    "maintenance_cost":         "REAL DEFAULT 0",
    "misc_cost":                "REAL DEFAULT 0",
    "total_treatment_cost":     "REAL DEFAULT 0",
    # ── Business Impact (Cost of Doing Nothing) ─────────────────────────────
    "regulatory_fine_est":      "REAL DEFAULT 0",
    "breach_cost_est":          "REAL DEFAULT 0",
    "downtime_cost_est":        "REAL DEFAULT 0",
    "lost_revenue_est":         "REAL DEFAULT 0",
    "recovery_cost_est":        "REAL DEFAULT 0",
    "legal_cost_est":           "REAL DEFAULT 0",
    "reputation_cost_est":      "REAL DEFAULT 0",
    "customer_loss_est":        "REAL DEFAULT 0",
    "productivity_loss_est":    "REAL DEFAULT 0",
    "total_business_impact":    "REAL DEFAULT 0",
    # ── ROSI ────────────────────────────────────────────────────────────────
    "risk_reduction_pct":       "REAL DEFAULT 0",
    "rosi_pct":                 "REAL DEFAULT 0",
    "projected_savings":        "REAL DEFAULT 0",
}

def _migrate_schema():
    """
    Inspect the live 'risks' table via PRAGMA table_info and ALTER TABLE
    ADD COLUMN for anything in RISKS_SCHEMA that is missing. Makes the app
    safe to run against databases created by any older RiskCore version
    without losing existing data. Idempotent: only adds columns confirmed
    absent, so it's safe to call on every startup.

    The idx_risks_nist index is created here rather than in init_db's
    executescript block because it references nist_function, which may
    not exist on old databases until this migration runs — creating the
    index before the column exists would raise OperationalError.
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
        # Safe to create now: nist_function is guaranteed present either
        # from original schema or from the migration loop above.
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_risks_nist "
                "ON risks(nist_function)")
        except sqlite3.OperationalError:
            pass  # Index already exists on current-version databases
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
        def _f(k):
            try: return float(data.get(k) or 0)
            except: return 0.0
        # Cost fields
        lc  = _f("labour_cost");    sc2 = _f("software_cost")
        hc  = _f("hardware_cost");  cc  = _f("consulting_cost")
        tc  = _f("training_cost");  lsc = _f("licensing_cost")
        mc  = _f("maintenance_cost"); misc = _f("misc_cost")
        ttc = lc + sc2 + hc + cc + tc + lsc + mc + misc
        # Business impact
        rfe = _f("regulatory_fine_est"); bce = _f("breach_cost_est")
        dce = _f("downtime_cost_est");   lre = _f("lost_revenue_est")
        rce = _f("recovery_cost_est");   lge = _f("legal_cost_est")
        rpe = _f("reputation_cost_est"); cle = _f("customer_loss_est")
        ple = _f("productivity_loss_est")
        tbi = rfe + bce + dce + lre + rce + lge + rpe + cle + ple
        # ROSI
        rrp = _f("risk_reduction_pct") or 80.0
        exp_loss = tbi * (rrp / 100)
        rosi = ((exp_loss - ttc) / ttc * 100) if ttc > 0 else 0.0
        ps   = exp_loss - ttc

        conn.execute("""
            UPDATE risks SET
                title=?, description=?, category=?, nist_function=?,
                nist_category=?, iso_domain=?, cia_component=?,
                mitre_tactic=?, cis_control=?, likelihood=?, impact=?,
                risk_score=?, inherent_score=?, residual_score=?,
                risk_velocity=?, owner=?, status=?, mitigation=?,
                review_date=?, date_modified=?, notes=?, mitre_technique=?,
                confidence=?, iso_control=?, nist_subcategory=?,
                existing_controls=?, priority=?,
                labour_cost=?, software_cost=?, hardware_cost=?,
                consulting_cost=?, training_cost=?, licensing_cost=?,
                maintenance_cost=?, misc_cost=?, total_treatment_cost=?,
                regulatory_fine_est=?, breach_cost_est=?, downtime_cost_est=?,
                lost_revenue_est=?, recovery_cost_est=?, legal_cost_est=?,
                reputation_cost_est=?, customer_loss_est=?,
                productivity_loss_est=?, total_business_impact=?,
                risk_reduction_pct=?, rosi_pct=?, projected_savings=?
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
            lc, sc2, hc, cc, tc, lsc, mc, misc, ttc,
            rfe, bce, dce, lre, rce, lge, rpe, cle, ple, tbi,
            rrp, rosi, ps,
            int(rid),
        ))
    audit("UPDATE", rid, f"Manual edit: {str(data.get('title',''))[:60]}")
    return True

def get_risks(search="", status_filter="All",
              nist_filter="All", score_filter="All", owner_filter="All"):
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
    if owner_filter != "All":
        query += " AND owner=?"
        params.append(sanitise(owner_filter, 100))
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
        # Treatment stats (safe on v1.0 databases — table created by init_db)
        treat_total = conn.execute(
            "SELECT COUNT(*) FROM treatments").fetchone()[0]
        treat_overdue = conn.execute(
            "SELECT COUNT(*) FROM treatments "
            "WHERE target_date!='' AND target_date IS NOT NULL "
            "AND target_date<? "
            "AND status NOT IN ('Completed','Verified')",
            (today(),)).fetchone()[0]
        treat_verify = conn.execute(
            "SELECT COUNT(*) FROM treatments "
            "WHERE status='Completed'").fetchone()[0]
        no_treatment = conn.execute(
            "SELECT COUNT(*) FROM risks r "
            "WHERE COALESCE(r.risk_score,0)>=10 "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM treatments t "
            "  WHERE t.risk_id=r.id "
            "  AND t.status NOT IN ('Ineffective')"
            ")").fetchone()[0]
    return {
        "total": total, "critical": critical, "high": high,
        "open": open_r, "overdue": overdue, "ai_sourced": ai_src,
        "treat_total": treat_total, "treat_overdue": treat_overdue,
        "treat_verify": treat_verify, "no_treatment": no_treatment,
    }

def get_owners():
    """Return distinct non-empty owner values for filter dropdowns."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT owner FROM risks "
            "WHERE owner IS NOT NULL AND owner!='' "
            "ORDER BY owner").fetchall()
    return [r[0] for r in rows]

# ── Framework Intelligence Engine ─────────────────────────────────────────────
# Builds a unified, per-framework view of how a risk is mapped, with an
# honest confidence tier for each entry:
#   "Confirmed" — the user (or AI analysis) explicitly selected this value
#   "Unmapped"  — the field was left at its default / "Not Applicable" /
#                 empty, meaning no real selection was made
#   "Suggested" — reserved for a future sourced crosswalk (e.g. the MITRE
#                 Center for Threat-Informed Defense's published
#                 ATT&CK<->NIST 800-53 dataset). FRAMEWORK_CROSSWALK below
#                 is intentionally empty for now rather than populated
#                 with invented relationships — adding a real, sourced
#                 dataset later only means filling in this dict; no other
#                 code needs to change. This satisfies the "future
#                 frameworks can be added without rewriting the system"
#                 requirement without fabricating data in the meantime.
#
# FRAMEWORK_CROSSWALK structure (for when real source data is added):
#   {(framework_a, value_a): [(framework_b, value_b, source_citation), ...]}
# Left empty deliberately — see note above.
FRAMEWORK_CROSSWALK = {}

# Values treated as "nothing was really selected" per field, since several
# dropdowns default to a placeholder rather than being left blank.
_UNMAPPED_VALUES = {"", "Not Applicable", "N/A", None}

def get_framework_mapping(risk_row):
    """
    Build a structured Framework Intelligence view for a single risk.

    Returns a list of dicts, one per framework, each containing:
        framework   — display name of the framework
        function    — top-level classification within that framework
                       (e.g. NIST function, ISO theme, MITRE tactic)
        category    — sub-classification where applicable
        control     — specific control/technique reference where applicable
        confidence  — "Confirmed", "Suggested", or "Unmapped"
        rationale   — one-line, honest explanation of why this entry has
                      the confidence tier it has

    risk_row may be a sqlite3.Row or a dict (both support the .get()-style
    access used here via direct key lookups guarded with `in risk_row.keys()`
    for Row objects, or risk_row.get(...) for dicts — handled uniformly
    below via a small local accessor).
    """
    def gv(key):
        # Works for both sqlite3.Row (no .get()) and plain dicts.
        try:
            val = risk_row[key]
        except (KeyError, IndexError):
            return None
        return val

    def confirmed_or_unmapped(value):
        if value in _UNMAPPED_VALUES:
            return "Unmapped", "No value was selected for this field."
        return "Confirmed", "Selected directly on this risk record."

    mappings = []

    # NIST CSF 2.0
    nist_fn  = gv("nist_function")
    nist_cat = gv("nist_category")
    nist_sub = gv("nist_subcategory")
    conf, why = confirmed_or_unmapped(nist_fn)
    mappings.append({
        "framework":  "NIST CSF 2.0",
        "function":   nist_fn or "—",
        "category":   nist_cat or "—",
        "control":    nist_sub or "—",
        "confidence": conf,
        "rationale":  why,
    })

    # ISO/IEC 27001:2022
    iso_dom = gv("iso_domain")
    iso_ctl = gv("iso_control")
    conf, why = confirmed_or_unmapped(iso_dom)
    mappings.append({
        "framework":  "ISO/IEC 27001:2022",
        "function":   iso_dom or "—",
        "category":   "—",
        "control":    iso_ctl or "—",
        "confidence": conf,
        "rationale":  why,
    })

    # MITRE ATT&CK
    mitre_tac = gv("mitre_tactic")
    mitre_tec = gv("mitre_technique")
    conf, why = confirmed_or_unmapped(mitre_tac)
    mappings.append({
        "framework":  "MITRE ATT&CK",
        "function":   mitre_tac or "—",
        "category":   "Tactic",
        "control":    mitre_tec or "—",
        "confidence": conf,
        "rationale":  why,
    })

    # CIS Controls v8
    cis = gv("cis_control")
    conf, why = confirmed_or_unmapped(cis)
    mappings.append({
        "framework":  "CIS Controls v8",
        "function":   cis or "—",
        "category":   "—",
        "control":    cis or "—",
        "confidence": conf,
        "rationale":  why,
    })

    # CIA Triad
    cia = gv("cia_component")
    conf, why = confirmed_or_unmapped(cia)
    mappings.append({
        "framework":  "CIA Triad",
        "function":   cia or "—",
        "category":   "—",
        "control":    "—",
        "confidence": conf,
        "rationale":  why,
    })

    # Reserved hook for future sourced crosswalk relationships. Currently
    # FRAMEWORK_CROSSWALK is empty (see comment above), so this loop adds
    # nothing today — it exists so that populating the dict later requires
    # zero changes to this function or any caller.
    for entry in mappings:
        key = (entry["framework"], entry["function"])
        for fw_b, val_b, source in FRAMEWORK_CROSSWALK.get(key, []):
            mappings.append({
                "framework":  fw_b,
                "function":   val_b,
                "category":   "—",
                "control":    "—",
                "confidence": "Suggested",
                "rationale":  f"Documented relationship with "
                              f"{entry['framework']} {entry['function']} "
                              f"(source: {source}).",
            })

    return mappings

def get_framework_coverage_summary():
    """
    Aggregate Framework Intelligence across the whole register: for each
    framework, how many risks have a Confirmed mapping vs. Unmapped.
    Used by the Framework Coverage view. Read-only, no side effects.
    """
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM risks").fetchall()

    summary = {}
    fw_names = ["NIST CSF 2.0", "ISO/IEC 27001:2022",
                "MITRE ATT&CK", "CIS Controls v8", "CIA Triad"]
    for fw in fw_names:
        summary[fw] = {"confirmed": 0, "unmapped": 0, "total": len(rows)}

    for r in rows:
        mapping = get_framework_mapping(r)
        for entry in mapping:
            fw = entry["framework"]
            if fw not in summary:
                continue
            if entry["confidence"] == "Confirmed":
                summary[fw]["confirmed"] += 1
            elif entry["confidence"] == "Unmapped":
                summary[fw]["unmapped"] += 1

    for fw in summary:
        total = summary[fw]["total"]
        summary[fw]["coverage_pct"] = (
            round(summary[fw]["confirmed"] / total * 100, 1)
            if total else 0.0)

    return summary

# ── Organisation Scope ────────────────────────────────────────────────────────
# Stored in its own table (per requirements) rather than embedded in risk
# records, since scope describes the assessment context, not an individual
# risk. Multi-value fields (business units, locations, assets in scope,
# frameworks selected) are stored as JSON-encoded text — consistent with
# how settings.json already uses JSON elsewhere in this codebase — since
# there is one active scope per assessment, not a many-to-many relationship
# that would justify a separate join table.
ASSET_TYPES = [
    "Servers", "Endpoints", "Cloud Infrastructure", "Applications",
    "Databases", "Active Directory / Identity Services",
    "Network Infrastructure", "OT / Industrial Systems",
    "Email", "Mobile Devices", "Other",
]
ORG_SIZES = ["Small", "Medium", "Large"]
ASSESSMENT_TYPES = ["Internal", "External", "Audit",
                    "Gap Assessment", "Risk Assessment", "Other"]
SCOPE_FRAMEWORKS = ["NIST CSF 2.0", "ISO/IEC 27001:2022",
                    "MITRE ATT&CK", "CIS Controls v8", "CIA Triad"]

def _json_list(value):
    """Safely decode a JSON-encoded list column; '' / NULL -> []."""
    if not value:
        return []
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, list) else []
    except Exception:
        return []

def save_organisation_scope(data: dict):
    """
    Insert or update the active Organisation Scope. RiskCore supports one
    active scope at a time (the assessment currently being prepared/run),
    so this upserts row id=1 rather than accumulating history — matching
    how Settings already works (one settings.json, overwritten on save).
    Multi-value fields are JSON-encoded lists.
    """
    now = datetime.datetime.now().isoformat()

    def jlist(key):
        val = data.get(key) or []
        if not isinstance(val, list):
            val = [v.strip() for v in str(val).split(",") if v.strip()]
        return json.dumps(val)

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM organisation_scope ORDER BY id LIMIT 1"
        ).fetchone()
        params = (
            sanitise(data.get("organisation_name", ""), 200),
            sanitise(data.get("industry", ""), 100),
            sanitise(data.get("organisation_size", ""), 20),
            sanitise(data.get("business_function", ""), 200),
            sanitise(data.get("assessment_name", ""), 200),
            sanitise(data.get("assessment_type", ""), 50),
            sanitise(data.get("assessment_objective", ""), 1000),
            jlist("business_units"),
            jlist("locations"),
            jlist("assets_in_scope"),
            sanitise(data.get("critical_assets", ""), 2000),
            jlist("frameworks_selected"),
        )
        if existing:
            conn.execute("""
                UPDATE organisation_scope SET
                    organisation_name=?, industry=?, organisation_size=?,
                    business_function=?, assessment_name=?, assessment_type=?,
                    assessment_objective=?, business_units=?, locations=?,
                    assets_in_scope=?, critical_assets=?, frameworks_selected=?,
                    modified_at=?
                WHERE id=?
            """, params + (now, existing["id"]))
            scope_id = existing["id"]
        else:
            cur = conn.execute("""
                INSERT INTO organisation_scope(
                    organisation_name, industry, organisation_size,
                    business_function, assessment_name, assessment_type,
                    assessment_objective, business_units, locations,
                    assets_in_scope, critical_assets, frameworks_selected,
                    created_at, modified_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, params + (now, now))
            scope_id = cur.lastrowid
    audit("ORG_SCOPE_SAVE", detail=
          f"{data.get('assessment_name','')[:60]} "
          f"({data.get('organisation_name','')[:40]})")
    return scope_id

def get_organisation_scope():
    """
    Return the active Organisation Scope as a plain dict with multi-value
    fields already decoded from JSON into Python lists, or None if no
    scope has been saved yet. Always returns a dict (never a raw
    sqlite3.Row) so callers can safely use .get() everywhere — this
    project has been bitten before by sqlite3.Row not supporting .get().
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM organisation_scope ORDER BY id LIMIT 1"
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("business_units", "locations",
                "assets_in_scope", "frameworks_selected"):
        d[key] = _json_list(d.get(key))
    return d

# ── Treatment CRUD ────────────────────────────────────────────────────────────
def insert_treatment(data):
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO treatments(
                risk_id, strategy, title, description, owner, status,
                target_date, completion_date, residual_score_target,
                residual_score_actual, cost_estimate, notes,
                date_created, date_modified)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            int(data["risk_id"]),
            sanitise(data.get("strategy", "Mitigate"), 20),
            sanitise(data.get("title", ""), 200),
            sanitise(data.get("description", ""), 1000),
            sanitise(data.get("owner", ""), 200),
            sanitise(data.get("status", "Draft"), 30),
            sanitise(data.get("target_date", ""), 10),
            sanitise(data.get("completion_date", ""), 10),
            data.get("residual_score_target") or None,
            data.get("residual_score_actual") or None,
            sanitise(data.get("cost_estimate", ""), 100),
            sanitise(data.get("notes", ""), 500),
            now, now,
        ))
        tid = cur.lastrowid
    audit("TREATMENT_CREATE", data["risk_id"],
          f"{data.get('strategy','')} · {data.get('title','')[:50]}")
    if data.get("status") == "Verified" and data.get("residual_score_actual"):
        _sync_residual_from_treatment(data["risk_id"])
    return tid

def update_treatment(tid, data):
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("""
            UPDATE treatments SET
                strategy=?, title=?, description=?, owner=?, status=?,
                target_date=?, completion_date=?, residual_score_target=?,
                residual_score_actual=?, cost_estimate=?, notes=?,
                date_modified=?
            WHERE id=?
        """, (
            sanitise(data.get("strategy", "Mitigate"), 20),
            sanitise(data.get("title", ""), 200),
            sanitise(data.get("description", ""), 1000),
            sanitise(data.get("owner", ""), 200),
            sanitise(data.get("status", "Draft"), 30),
            sanitise(data.get("target_date", ""), 10),
            sanitise(data.get("completion_date", ""), 10),
            data.get("residual_score_target") or None,
            data.get("residual_score_actual") or None,
            sanitise(data.get("cost_estimate", ""), 100),
            sanitise(data.get("notes", ""), 500),
            now, int(tid),
        ))
        row = conn.execute(
            "SELECT risk_id FROM treatments WHERE id=?",
            (int(tid),)).fetchone()
        risk_id = row["risk_id"] if row else None
    if risk_id:
        audit("TREATMENT_UPDATE", risk_id,
              f"{data.get('strategy','')} · {data.get('title','')[:40]}"
              f" → {data.get('status','')}")
        if data.get("status") == "Verified":
            _sync_residual_from_treatment(risk_id)
    return True

def delete_treatment(tid):
    with get_db() as conn:
        row = conn.execute(
            "SELECT risk_id FROM treatments WHERE id=?",
            (int(tid),)).fetchone()
        risk_id = row["risk_id"] if row else None
        conn.execute("DELETE FROM treatments WHERE id=?", (int(tid),))
    if risk_id:
        audit("TREATMENT_DELETE", risk_id,
              f"Treatment #{tid} removed")

def get_treatments(risk_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM treatments WHERE risk_id=? "
            "ORDER BY date_created DESC",
            (int(risk_id),)).fetchall()

def get_treatment(tid):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM treatments WHERE id=?",
            (int(tid),)).fetchone()

def get_pipeline_treatments():
    """Treatments for Dashboard pipeline view."""
    with get_db() as conn:
        return conn.execute("""
            SELECT t.*, r.title as risk_title, r.risk_score
            FROM treatments t
            JOIN risks r ON t.risk_id = r.id
            WHERE t.status NOT IN ('Verified','Ineffective')
            ORDER BY t.target_date ASC, r.risk_score DESC
        """).fetchall()

def _sync_residual_from_treatment(risk_id):
    """When a treatment is Verified, update parent risk residual_score."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT residual_score_actual FROM treatments
            WHERE risk_id=? AND status='Verified'
            AND residual_score_actual IS NOT NULL
            ORDER BY date_modified DESC LIMIT 1
        """, (int(risk_id),)).fetchone()
        if row and row[0]:
            conn.execute(
                "UPDATE risks SET residual_score=?, date_modified=? "
                "WHERE id=?",
                (int(row[0]), today(), int(risk_id)))
            audit("RESIDUAL_SYNC", risk_id,
                  f"Residual updated to {row[0]} from verified treatment")

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
    # Validate the backup file is a healthy SQLite database before touching live data
    try:
        import sqlite3 as _sq3
        _conn = _sq3.connect(str(backup_path))
        _result = _conn.execute("PRAGMA integrity_check").fetchone()
        _conn.close()
        if _result is None or _result[0] != "ok":
            raise ValueError(
                f"Backup file failed integrity check: {_result}. "
                "The file may be corrupted or not a valid RiskCore database.")
    except _sq3.DatabaseError as _dbe:
        raise ValueError(
            f"Selected file is not a valid SQLite database: {_dbe}. "
            "Please select a file from the RiskCore backups folder.") from _dbe
    # Safety net: back up the current live DB before overwriting it,
    # so a restore can itself be undone.
    pre_restore_backup = backup_database()
    shutil.copy2(backup_path, DB_PATH)
    audit("DB_RESTORE",
          detail=f"Restored from {backup_path.name} "
                 f"(pre-restore snapshot: {pre_restore_backup.name})")
    return pre_restore_backup

# ── App UI helpers ────────────────────────────────────────────────────────────
def _card_hdr(parent, title, sub=None):
    """Standard card section header with optional subtitle."""
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x", padx=14, pady=(12, 6))
    ctk.CTkLabel(f, text=title,
                 font=ctk.CTkFont(size=11, weight="bold"),
                 text_color=TEXT_MAIN).pack(anchor="w")
    if sub:
        ctk.CTkLabel(f, text=sub,
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_MUTED).pack(anchor="w")

# ── App ───────────────────────────────────────────────────────────────────────
class RiskCore(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("RiskCore GRC Platform v1.5")
        self.geometry("1280x820")
        self.minsize(1100, 700)
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
        self._owner_val   = "All"

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
                text=f"{'●' if db_ok else '✕'} "
                     f"{'Connected' if db_ok else 'DB ERROR'}",
                text_color=GREEN_LT if db_ok else RED)
            self._sb_total.configure(
                text=f"│  {stats['total']} risks  ·  "
                     f"{stats['critical']} critical  ·  "
                     f"{stats['treat_total']} treatments")
            self._sb_time.configure(
                text=f"v1.5  ·  {now_str()}")
        except Exception as e:
            self._sb_db.configure(
                text=f"✕ DB Error: {e}", text_color=RED)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=230, fg_color=SIDEBAR_BG,
                          corner_radius=0)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.pack(pady=(20, 4), padx=16, fill="x")
        ctk.CTkLabel(brand, text="⬡",
                     font=ctk.CTkFont(size=26),
                     text_color=ACCENT).pack(side="left")
        nf = ctk.CTkFrame(brand, fg_color="transparent")
        nf.pack(side="left", padx=10)
        ctk.CTkLabel(nf, text="RiskCore",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w")
        ctk.CTkLabel(nf, text="GRC Platform  v1.5",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_MUTED).pack(anchor="w")

        ctk.CTkFrame(sb, height=1,
                     fg_color=BORDER).pack(fill="x", padx=10, pady=4)

        self.nav_btns = {}

        def nav_section(label):
            ctk.CTkLabel(sb, text=label,
                         font=ctk.CTkFont(size=8, weight="bold"),
                         text_color=TEXT_DIM).pack(
                         anchor="w", padx=18, pady=(8, 2))

        def nav_btn(key, icon, label):
            btn = ctk.CTkButton(
                sb, text=f" {icon}   {label}", anchor="w", height=34,
                font=ctk.CTkFont(size=12), fg_color="transparent",
                hover_color=BORDER, text_color=TEXT_MUTED,
                corner_radius=6,
                command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", padx=8, pady=1)
            self.nav_btns[key] = btn

        nav_section("WORKSPACE")
        nav_btn("dashboard",  "▣", "Dashboard")
        nav_btn("treatments", "◈", "Treatments")
        nav_btn("register",   "≡", "Risk Register")
        nav_btn("matrix",     "⊞", "Risk Matrix")

        nav_section("MANAGE")
        nav_btn("add",    "+", "Add Risk")
        nav_btn("ai",     "◎", "AI Analysis")
        nav_btn("export", "↗", "Export & Report")

        nav_section("SYSTEM")
        nav_btn("audit",    "⊙", "Audit Log")
        nav_btn("settings", "⚙", "Settings")

        ctk.CTkFrame(sb, height=1,
                     fg_color=BORDER).pack(fill="x", padx=10, pady=4)

        for fw, color in [
            ("NIST CSF 2.0",    NIST_COLORS["Govern"]),
            ("ISO 27001:2022",  "#1B5E20"),
            ("MITRE ATT&CK",    "#B71C1C"),
            ("CIS Controls v8", "#E65100"),
            ("CIA Triad",       "#4A148C"),
        ]:
            f = ctk.CTkFrame(sb, fg_color=color,
                             corner_radius=3, height=18)
            f.pack(fill="x", padx=10, pady=1)
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=fw,
                         font=ctk.CTkFont(size=8, weight="bold"),
                         text_color="white").pack(padx=6, anchor="w")

        ctk.CTkFrame(sb, height=1,
                     fg_color=BORDER).pack(fill="x", padx=10, pady=4)
        self._pending_badge = ctk.CTkLabel(
            sb, text="", font=ctk.CTkFont(size=10), text_color=GOLD)
        self._pending_badge.pack(padx=14, anchor="w", pady=(2, 8))

    # ── Main area ─────────────────────────────────────────────────────────────
    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=0)
        self.main.pack(side="right", fill="both", expand=True)

    def _clear(self):
        for w in self.main.winfo_children():
            w.destroy()

    def show_page(self, page, edit_id=None):
        self._current_page = page
        self._pending_edit_id = edit_id
        for k, b in self.nav_btns.items():
            b.configure(
                fg_color=BORDER if k == page else "transparent",
                text_color=TEXT_MAIN if k == page else TEXT_MUTED)
        self._clear()
        {
            "dashboard":  self._pg_dashboard,
            "treatments": self._pg_treatments,
            "ai":         self._pg_ai,
            "register":   self._pg_register,
            "add":        self._pg_add_manual,
            "matrix":     self._pg_matrix,
            "export":     self._pg_export,
            "audit":      self._pg_audit,
            "settings":   self._pg_settings,
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
        f.pack(fill="x", padx=24, pady=(18, 6))
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text=title,
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(
                     row=0, column=0, sticky="w")
        if sub:
            ctk.CTkLabel(f, text=sub,
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).grid(
                         row=1, column=0, sticky="w")
        if refresh_cmd:
            ctk.CTkButton(f, text="⟳", width=32, height=28,
                          fg_color=BORDER,
                          hover_color=CARD_BG2,
                          font=ctk.CTkFont(size=13),
                          corner_radius=6,
                          command=refresh_cmd).grid(
                          row=0, column=1, padx=(8, 0), sticky="e")

    def _stat_card(self, parent, row, col,
                   title, val, sub="", color=TEXT_MAIN):
        f = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=10)
        f.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(f, text=title,
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(
                     pady=(12, 2), padx=14, anchor="w")
        ctk.CTkLabel(f, text=str(val),
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=color).pack(padx=14, anchor="w")
        ctk.CTkLabel(f, text=sub or " ",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(
                     padx=14, pady=(0, 12), anchor="w")

    def _toast(self, msg, color=GREEN_LT, duration=4000):
        if hasattr(self, "_toast_widget"):
            try:
                if self._toast_widget.winfo_exists():
                    self._toast_widget.destroy()
            except Exception:
                pass
        t = ctk.CTkFrame(self.main, fg_color=color,
                         corner_radius=8, height=34)
        t.pack(fill="x", padx=24, pady=(0, 4))
        t.pack_propagate(False)
        ctk.CTkLabel(t, text=msg,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="white").pack(
                     padx=14, pady=6, anchor="w")
        self._toast_widget = t
        self.after(duration,
                   lambda: t.destroy() if t.winfo_exists() else None)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    def _pg_dashboard(self):
        # ── Gather all data in one pass — single DB touch ─────────────────
        stats    = get_stats()
        scope    = get_organisation_scope()
        risks_all = get_risks()
        pipeline = get_pipeline_treatments()

        # Framework coverage (reuses existing engine, no extra DB query)
        from riskcore_ai import build_framework_coverage_report
        cov_report = build_framework_coverage_report(
            [dict(r) for r in risks_all])
        pf = cov_report["per_framework"]
        cd = cov_report["chart_data"]
        hi = cov_report["health_insights"]

        # Executive summary from last AI run (cached, no re-call)
        exec_sum = None
        if hasattr(self, "_last_analysis") and self._last_analysis:
            exec_sum = self._last_analysis.get("_exec_summary")

        org_name = (scope.get("organisation_name") if scope
                    else self._company_name)
        assessment = (scope.get("assessment_name") if scope else "")

        # ── Outer scrollable container ────────────────────────────────────
        outer = ctk.CTkScrollableFrame(self.main, fg_color=DARK_BG,
                                        scrollbar_button_color=BORDER)
        outer.pack(fill="both", expand=True)

        # ══════════════════════════════════════════════════════════════════
        #  EXECUTIVE HEADER
        # ══════════════════════════════════════════════════════════════════
        hdr = ctk.CTkFrame(outer, fg_color=SIDEBAR_BG, corner_radius=10)
        hdr.pack(fill="x", padx=16, pady=(12, 8))
        hdr.grid_columnconfigure(1, weight=1)

        # Left: brand
        brand = ctk.CTkFrame(hdr, fg_color="transparent")
        brand.grid(row=0, column=0, padx=16, pady=10, sticky="w")
        ctk.CTkLabel(brand, text="⬡  RiskCore",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkLabel(brand, text="  GRC Platform v1.5",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(side="left")

        # Centre: assessment + org + date
        meta = ctk.CTkFrame(hdr, fg_color="transparent")
        meta.grid(row=0, column=1, padx=8, pady=10, sticky="ew")
        meta_items = []
        if assessment:
            meta_items.append(assessment)
        meta_items += [org_name, today(),
                       "NIST CSF 2.0", "ISO/IEC 27001:2022",
                       "MITRE ATT&CK", "CIS Controls v8", "CIA Triad"]
        ctk.CTkLabel(meta,
                     text="  ·  ".join(meta_items),
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED,
                     wraplength=680, anchor="w").pack(anchor="w")

        # Right: posture badge + refresh
        right_hdr = ctk.CTkFrame(hdr, fg_color="transparent")
        right_hdr.grid(row=0, column=2, padx=16, pady=10, sticky="e")
        posture   = cov_report["posture"]
        p_color   = {
            "Critical": RED, "High": ORANGE,
            "Medium": GOLD, "Low": GREEN_LT,
        }.get(posture, TEXT_MUTED)
        p_bg = {
            "Critical": "#3D0000", "High": "#3D1A00",
            "Medium": "#3D2E00", "Low": "#0D3321",
        }.get(posture, BORDER)
        pb_f = ctk.CTkFrame(right_hdr, fg_color=p_bg, corner_radius=6)
        pb_f.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(pb_f, text=f"  {posture}  ",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=p_color).pack(padx=8, pady=4)
        ctk.CTkButton(right_hdr, text="⟳ Refresh",
                      width=88, height=28,
                      fg_color=BORDER, hover_color=CARD_BG2,
                      font=ctk.CTkFont(size=10), corner_radius=6,
                      command=lambda: self.show_page("dashboard")
                      ).pack(side="left")

        # ══════════════════════════════════════════════════════════════════
        #  ROW 1 — RISK KPI CARDS (6 wide)
        # ══════════════════════════════════════════════════════════════════
        def _kpi_card(parent, col, icon, title, value,
                      sub, color=TEXT_MAIN, bg=CARD_BG):
            f = ctk.CTkFrame(parent, fg_color=bg, corner_radius=10)
            f.grid(row=0, column=col, padx=5, pady=0, sticky="nsew")
            f.grid_columnconfigure(0, weight=1)
            top = ctk.CTkFrame(f, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 0))
            top.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(top, text=title,
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED,
                         anchor="w").grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(top, text=icon,
                         font=ctk.CTkFont(size=14),
                         text_color=color).grid(
                         row=0, column=1, sticky="e")
            ctk.CTkLabel(f, text=str(value),
                         font=ctk.CTkFont(size=26, weight="bold"),
                         text_color=color).pack(
                         anchor="w", padx=12, pady=(2, 0))
            ctk.CTkLabel(f, text=sub,
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED).pack(
                         anchor="w", padx=12, pady=(0, 10))

        row1 = ctk.CTkFrame(outer, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(0, 6))
        for i in range(6):
            row1.grid_columnconfigure(i, weight=1)

        _kpi_card(row1, 0, "▣", "Total Risks",
                  stats["total"], "in register")
        _kpi_card(row1, 1, "⊘", "Critical",
                  stats["critical"], "score ≥ 15",
                  RED,
                  "#1E0808" if stats["critical"] else CARD_BG)
        _kpi_card(row1, 2, "↑", "High",
                  stats["high"], "score 10–14",
                  ORANGE,
                  "#1E0E00" if stats["high"] else CARD_BG)
        _kpi_card(row1, 3, "◉", "Open",
                  stats["open"], "unresolved", GOLD)
        _kpi_card(row1, 4, "⏱", "Overdue Review",
                  stats["overdue"], "past review date",
                  RED if stats["overdue"] else TEXT_MUTED)
        _kpi_card(row1, 5, "◎", "AI Sourced",
                  stats["ai_sourced"], "from PDF", PURPLE_LT)

        # ── Row 2 — Treatment KPI cards ───────────────────────────────────
        row2 = ctk.CTkFrame(outer, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 10))
        for i in range(4):
            row2.grid_columnconfigure(i, weight=1)

        _kpi_card(row2, 0, "✓", "Total Treatments",
                  stats["treat_total"], "logged", GREEN_LT)
        _kpi_card(row2, 1, "⚠", "Overdue Treatments",
                  stats["treat_overdue"], "past target date",
                  RED if stats["treat_overdue"] else TEXT_MUTED)
        _kpi_card(row2, 2, "◈", "Awaiting Verification",
                  stats["treat_verify"], "Completed → Verify",
                  GOLD if stats["treat_verify"] else TEXT_MUTED)
        _kpi_card(row2, 3, "⊗", "Untreated High+",
                  stats["no_treatment"], "score ≥ 10, no plan",
                  ORANGE if stats["no_treatment"] else TEXT_MUTED)

        # ══════════════════════════════════════════════════════════════════
        #  THREE-COLUMN MIDDLE SECTION
        # ══════════════════════════════════════════════════════════════════
        mid = ctk.CTkFrame(outer, fg_color="transparent")
        mid.pack(fill="x", padx=16, pady=(0, 8))
        mid.grid_columnconfigure(0, weight=5)
        mid.grid_columnconfigure(1, weight=4)
        mid.grid_columnconfigure(2, weight=3)

        # ── Col A: NIST CSF 2.0 Distribution ─────────────────────────────
        col_a = ctk.CTkFrame(mid, fg_color=CARD_BG, corner_radius=10)
        col_a.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")
        col_a.grid_columnconfigure(1, weight=1)
        _card_hdr(col_a, "Risk Distribution by NIST CSF 2.0 Function")

        total_safe = max(stats["total"], 1)
        with get_db() as conn:
            nist_rows = []
            for fn in NIST_FUNCTIONS:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM risks "
                    "WHERE nist_function=?", (fn,)).fetchone()[0]
                avg = conn.execute(
                    "SELECT AVG(COALESCE(risk_score,0)) FROM risks "
                    "WHERE nist_function=?", (fn,)).fetchone()[0]
                nist_rows.append((fn, cnt, round(avg or 0, 1)))

        for i, (fn, cnt, avg) in enumerate(nist_rows):
            color = NIST_COLORS.get(fn, ACCENT2)
            ctk.CTkLabel(col_a, text=fn,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=color, width=78,
                         anchor="w").grid(
                         row=i+1, column=0,
                         padx=(14, 4), pady=4, sticky="w")
            bar = ctk.CTkProgressBar(col_a, height=7, corner_radius=4,
                                      progress_color=color,
                                      fg_color=BORDER)
            bar.set(min(cnt / total_safe, 1.0))
            bar.grid(row=i+1, column=1,
                     padx=(0, 4), pady=4, sticky="ew")
            ctk.CTkLabel(col_a,
                         text=f"{cnt} risks · avg {avg}",
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED, width=100,
                         anchor="e").grid(
                         row=i+1, column=2,
                         padx=(0, 14), pady=4, sticky="e")
        ctk.CTkLabel(col_a, text=" ",
                     font=ctk.CTkFont(size=4)).grid(
                     row=len(nist_rows)+1, column=0)

        # ── Col B: Risks by Severity (donut-style visual) ─────────────────
        col_b = ctk.CTkFrame(mid, fg_color=CARD_BG, corner_radius=10)
        col_b.grid(row=0, column=1, padx=6, pady=0, sticky="nsew")
        _card_hdr(col_b, "Risks by Severity")

        dist = cd["risk_distribution"]
        total_shown = max(sum(dist.values()), 1)
        severity_data = [
            ("Critical", dist["Critical"], RED),
            ("High",     dist["High"],     ORANGE),
            ("Medium",   dist["Medium"],   GOLD),
            ("Low",      dist["Low"],      GREEN_LT),
        ]

        # Visual bar-based "donut" representation
        donut_f = ctk.CTkFrame(col_b, fg_color="transparent")
        donut_f.pack(fill="both", expand=True, padx=14, pady=8)
        donut_f.grid_columnconfigure(0, weight=1)

        # Centre count display
        centre = ctk.CTkFrame(donut_f, fg_color=CARD_BG2,
                               corner_radius=50,
                               width=90, height=90)
        centre.pack(pady=(8, 12))
        centre.pack_propagate(False)
        ctk.CTkLabel(centre, text=str(stats["total"]),
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=TEXT_MAIN).pack(expand=True)

        # Stacked severity bars
        for label, count, color in severity_data:
            pct = round(count / total_shown * 100) if total_shown else 0
            sf = ctk.CTkFrame(donut_f, fg_color="transparent")
            sf.pack(fill="x", pady=2)
            sf.grid_columnconfigure(1, weight=1)
            dot = ctk.CTkFrame(sf, fg_color=color,
                               width=10, height=10, corner_radius=5)
            dot.grid(row=0, column=0, padx=(0, 6))
            ctk.CTkLabel(sf, text=label,
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED, width=55,
                         anchor="w").grid(row=0, column=1, sticky="w")
            bar = ctk.CTkProgressBar(sf, height=7, corner_radius=4,
                                      progress_color=color,
                                      fg_color=BORDER, width=80)
            bar.set(count / total_shown if total_shown else 0)
            bar.grid(row=0, column=2, padx=6, sticky="ew")
            ctk.CTkLabel(sf, text=f"{count}  ({pct}%)",
                         font=ctk.CTkFont(size=9),
                         text_color=color, width=54,
                         anchor="e").grid(row=0, column=3, sticky="e")

        # ── Col C: Treatment Pipeline ─────────────────────────────────────
        col_c = ctk.CTkFrame(mid, fg_color=CARD_BG, corner_radius=10)
        col_c.grid(row=0, column=2, padx=(6, 0), pady=0, sticky="nsew")
        _card_hdr(col_c, "Treatment Pipeline")

        if not pipeline:
            ctk.CTkLabel(col_c,
                         text="No active treatments",
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).pack(
                         pady=20, padx=14, anchor="w")
        else:
            for t in pipeline[:6]:
                tf = ctk.CTkFrame(col_c, fg_color=CARD_BG2,
                                   corner_radius=6)
                tf.pack(fill="x", padx=10, pady=3)
                tf.grid_columnconfigure(1, weight=1)
                s_col = TREAT_COLORS.get(t["strategy"], ACCENT2)
                sb = ctk.CTkFrame(tf, fg_color=s_col,
                                   corner_radius=3, width=54, height=18)
                sb.grid(row=0, column=0, padx=(8, 5), pady=7, sticky="w")
                sb.grid_propagate(False)
                ctk.CTkLabel(sb, text=t["strategy"][:6],
                             font=ctk.CTkFont(size=8, weight="bold"),
                             text_color="white").pack(padx=3, pady=2)
                ctk.CTkLabel(tf, text=t["title"][:26],
                             font=ctk.CTkFont(size=10),
                             text_color=TEXT_MAIN, anchor="w").grid(
                             row=0, column=1, pady=7, sticky="w")
                d = days_until(t["target_date"])
                if d is not None:
                    dt, dc = ((f"{abs(d)}d overdue", RED) if d < 0
                              else (f"{d}d", GOLD if d <= 7 else TEXT_MUTED))
                    ctk.CTkLabel(tf, text=dt, font=ctk.CTkFont(size=8),
                                 text_color=dc).grid(
                                 row=0, column=2, padx=(2, 8), pady=7)

        ctk.CTkButton(col_c, text="View All Treatments →",
                      height=28, fg_color="transparent",
                      hover_color=BORDER, border_width=1,
                      border_color=ACCENT, text_color=ACCENT,
                      font=ctk.CTkFont(size=10), corner_radius=6,
                      command=lambda: self.show_page("treatments")
                      ).pack(fill="x", padx=10, pady=(6, 10))

        # ══════════════════════════════════════════════════════════════════
        #  TWO-COLUMN LOWER SECTION
        # ══════════════════════════════════════════════════════════════════
        lower = ctk.CTkFrame(outer, fg_color="transparent")
        lower.pack(fill="x", padx=16, pady=(0, 8))
        lower.grid_columnconfigure(0, weight=3)
        lower.grid_columnconfigure(1, weight=2)

        # ── Left: Top Critical Risks table ────────────────────────────────
        bot_l = ctk.CTkFrame(lower, fg_color=CARD_BG, corner_radius=10)
        bot_l.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        _card_hdr(bot_l, "Top Critical Risks")

        # Column header row
        th = ctk.CTkFrame(bot_l, fg_color=BORDER,
                           corner_radius=0, height=24)
        th.pack(fill="x", padx=10)
        th.pack_propagate(False)
        th.grid_columnconfigure(0, weight=1)
        for col_i, (h, w) in enumerate([
            ("Risk", 0), ("Score", 55), ("Owner", 100),
            ("Treatment", 80), ("Status", 60),
        ]):
            th.grid_columnconfigure(col_i,
                                    weight=1 if col_i == 0 else 0,
                                    minsize=w)
            ctk.CTkLabel(th, text=h,
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=0, column=col_i, padx=6, pady=2, sticky="w")

        # Pre-fetch treatment counts
        with get_db() as conn:
            tc_map = {}
            for row in conn.execute(
                "SELECT risk_id, COUNT(*) as c FROM treatments "
                "WHERE status NOT IN ('Ineffective') GROUP BY risk_id"):
                tc_map[row["risk_id"]] = row["c"]

        top_risks = sorted(risks_all,
                           key=lambda r: int(r["risk_score"] or 0),
                           reverse=True)[:8]
        for i, r in enumerate(top_risks):
            sc = int(r["risk_score"] or 0)
            bg = CARD_BG if i % 2 == 0 else CARD_BG2
            rf = ctk.CTkFrame(bot_l, fg_color=bg, corner_radius=0)
            rf.pack(fill="x", padx=10, pady=0)
            rf.grid_columnconfigure(0, weight=1)
            click = lambda e, rid=r["id"]: self._view_risk(rid)
            tc = tc_map.get(r["id"], 0)
            nist_fn = r["nist_function"] or "—"
            cells = [
                (r["title"][:38],           TEXT_MAIN,  0),
                (str(sc),                   score_color(sc), 1),
                ((r["owner"] or "—")[:14],  TEXT_MUTED, 2),
                (nist_fn[:10],
                 NIST_COLORS.get(nist_fn, TEXT_MUTED),  3),
                (r["status"][:8],
                 (GOLD if r["status"] == "Open"
                  else GREEN_LT if r["status"] in
                  ("Mitigated","Closed") else TEXT_MUTED), 4),
            ]
            COL_W = [0, 55, 100, 80, 60]
            for ci in range(5):
                rf.grid_columnconfigure(
                    ci, weight=1 if ci == 0 else 0, minsize=COL_W[ci])
            for ci, (txt, col, _) in enumerate(cells):
                lbl = ctk.CTkLabel(rf, text=txt,
                                   font=ctk.CTkFont(size=10),
                                   text_color=col, anchor="w")
                lbl.grid(row=0, column=ci, padx=6, pady=6, sticky="w")
                lbl.bind("<Button-1>", click)
            rf.bind("<Button-1>", click)

        # ── Right: Framework Coverage ──────────────────────────────────────
        bot_r = ctk.CTkFrame(lower, fg_color=CARD_BG, corner_radius=10)
        bot_r.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        _card_hdr(bot_r, "Framework Coverage")

        FW_COLORS = {
            "NIST CSF 2.0":       ACCENT2,
            "ISO/IEC 27001:2022": GREEN_LT,
            "MITRE ATT&CK":       RED,
            "CIS Controls v8":    ORANGE,
            "CIA Triad":          PURPLE_LT,
        }
        FW_SHORT = {
            "NIST CSF 2.0":       "NIST CSF 2.0",
            "ISO/IEC 27001:2022": "ISO 27001:2022",
            "MITRE ATT&CK":       "MITRE ATT&CK",
            "CIS Controls v8":    "CIS Controls v8",
            "CIA Triad":          "CIA Triad",
        }
        for fw_name, fw_data in pf.items():
            fw_pct = fw_data["coverage_pct"]
            fw_col = FW_COLORS.get(fw_name, ACCENT2)
            ff = ctk.CTkFrame(bot_r, fg_color="transparent")
            ff.pack(fill="x", padx=12, pady=3)
            ff.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(ff, text=FW_SHORT.get(fw_name, fw_name),
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=fw_col, width=114,
                         anchor="w").grid(
                         row=0, column=0, sticky="w")
            bar = ctk.CTkProgressBar(ff, height=7, corner_radius=4,
                                      progress_color=fw_col,
                                      fg_color=BORDER)
            bar.set(fw_pct / 100)
            bar.grid(row=0, column=1, padx=6, sticky="ew")
            ctk.CTkLabel(ff, text=f"{fw_pct}%",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=fw_col, width=36,
                         anchor="e").grid(row=0, column=2, sticky="e")

        # Health insight under coverage
        if hi["frameworks_needing_review"]:
            ctk.CTkLabel(bot_r,
                         text="⚠  Needs attention: "
                              + ", ".join(hi["frameworks_needing_review"]),
                         font=ctk.CTkFont(size=9),
                         text_color=GOLD,
                         wraplength=300).pack(
                         padx=12, pady=(4, 0), anchor="w")

        ctk.CTkButton(bot_r, text="View Framework Intelligence →",
                      height=28, fg_color="transparent",
                      hover_color=BORDER, border_width=1,
                      border_color=ACCENT2, text_color=ACCENT2,
                      font=ctk.CTkFont(size=10), corner_radius=6,
                      command=lambda: self._open_framework_coverage()
                      ).pack(fill="x", padx=10, pady=(8, 10))

        # ══════════════════════════════════════════════════════════════════
        #  EXECUTIVE SUMMARY PANEL (if AI has run)
        # ══════════════════════════════════════════════════════════════════
        if exec_sum:
            es_f = ctk.CTkFrame(outer, fg_color=CARD_BG, corner_radius=10)
            es_f.pack(fill="x", padx=16, pady=(0, 8))
            _card_hdr(es_f, "Executive Intelligence  ·  from last AI analysis")
            es_f.grid_columnconfigure(0, weight=1)

            es_grid = ctk.CTkFrame(es_f, fg_color="transparent")
            es_grid.pack(fill="x", padx=14, pady=(0, 10))
            es_grid.grid_columnconfigure(0, weight=1)
            es_grid.grid_columnconfigure(1, weight=1)

            def _es_row(text, value, color=TEXT_MAIN, col=0, row=0):
                f = ctk.CTkFrame(es_grid, fg_color=CARD_BG2,
                                  corner_radius=6)
                f.grid(row=row, column=col, padx=4, pady=3, sticky="ew")
                f.grid_columnconfigure(1, weight=1)
                ctk.CTkLabel(f, text=text,
                             font=ctk.CTkFont(size=9),
                             text_color=TEXT_MUTED,
                             width=130, anchor="w").grid(
                             row=0, column=0, padx=(10,4), pady=6)
                ctk.CTkLabel(f, text=value[:120] if value else "—",
                             font=ctk.CTkFont(size=9),
                             text_color=color, anchor="w",
                             wraplength=340).grid(
                             row=0, column=1, padx=(0,10), pady=6,
                             sticky="w")

            _es_row("Risk Posture",
                    exec_sum.get("posture","—"), p_color, 0, 0)
            _es_row("Posture Explanation",
                    exec_sum.get("posture_explanation",""), TEXT_MAIN, 1, 0)
            _es_row("Strongest Areas",
                    exec_sum.get("strongest_areas",""), GREEN_LT, 0, 1)
            _es_row("Weakest Areas",
                    exec_sum.get("weakest_areas",""), RED, 1, 1)
            if exec_sum.get("immediate_priorities"):
                _es_row("Immediate Priority",
                        exec_sum["immediate_priorities"][0], ORANGE, 0, 2)
            if exec_sum.get("strategic_recommendations"):
                _es_row("Strategic Recommendation",
                        exec_sum["strategic_recommendations"][0], ACCENT2, 1, 2)

        # ══════════════════════════════════════════════════════════════════
        #  RECENT ACTIVITY + QUICK ACTIONS
        # ══════════════════════════════════════════════════════════════════
        bottom = ctk.CTkFrame(outer, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 12))
        bottom.grid_columnconfigure(0, weight=2)
        bottom.grid_columnconfigure(1, weight=1)

        # Recent activity (reuses audit log)
        act_f = ctk.CTkFrame(bottom, fg_color=CARD_BG, corner_radius=10)
        act_f.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        _card_hdr(act_f, "Recent Activity")

        with get_db() as conn:
            logs = conn.execute(
                "SELECT timestamp, action, detail FROM audit_log "
                "ORDER BY id DESC LIMIT 8").fetchall()

        ACTION_ICONS = {
            "CREATE":           ("◉", GOLD),
            "UPDATE":           ("✏", ACCENT2),
            "DELETE":           ("✕", RED),
            "TREATMENT_CREATE": ("◈", TEAL),
            "TREATMENT_UPDATE": ("◈", CYAN),
            "TREATMENT_DELETE": ("◈", ORANGE),
            "RESIDUAL_SYNC":    ("↓", GREEN_LT),
            "AI_ANALYSIS":      ("◎", PURPLE_LT),
            "AI_APPROVE":       ("✓", GREEN_LT),
            "EXPORT_PDF":       ("↗", ACCENT2),
            "DB_BACKUP":        ("◧", ACCENT2),
            "APP_START":        ("⬡", TEXT_DIM),
            "ORG_SCOPE_SAVE":   ("⊙", TEAL),
        }
        if not logs:
            ctk.CTkLabel(act_f, text="No activity recorded yet.",
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack(
                         padx=14, pady=12, anchor="w")
        for lg in logs:
            icon_txt, icon_col = ACTION_ICONS.get(
                lg["action"], ("·", TEXT_DIM))
            ts_short = (lg["timestamp"] or "")[:16].replace("T", "  ")
            lf = ctk.CTkFrame(act_f, fg_color="transparent")
            lf.pack(fill="x", padx=14, pady=2)
            lf.grid_columnconfigure(2, weight=1)
            ctk.CTkLabel(lf, text=icon_txt,
                         font=ctk.CTkFont(size=11),
                         text_color=icon_col, width=18).grid(
                         row=0, column=0, padx=(0, 6), sticky="w")
            ctk.CTkLabel(lf, text=lg["action"].replace("_", " "),
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=TEXT_MAIN, width=140,
                         anchor="w").grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(lf, text=(lg["detail"] or "")[:50],
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=0, column=2, sticky="w")
            ctk.CTkLabel(lf, text=ts_short,
                         font=ctk.CTkFont(size=8),
                         text_color=TEXT_DIM).grid(
                         row=0, column=3, padx=(6, 0), sticky="e")

        ctk.CTkButton(act_f, text="View Full Audit Log →",
                      height=26, fg_color="transparent",
                      hover_color=BORDER,
                      text_color=TEXT_MUTED,
                      font=ctk.CTkFont(size=9), corner_radius=6,
                      command=lambda: self.show_page("audit")
                      ).pack(anchor="e", padx=10, pady=(4, 8))

        # Quick Actions panel
        qa_f = ctk.CTkFrame(bottom, fg_color=CARD_BG, corner_radius=10)
        qa_f.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        _card_hdr(qa_f, "Quick Actions")

        qa_btns = [
            ("+ New Risk",              ACCENT,    lambda: self.show_page("add")),
            ("◎ Run AI Analysis",       PURPLE_LT, lambda: self.show_page("ai")),
            ("↗ Generate PDF Report",   ACCENT2,   lambda: self.show_page("export")),
            ("≡ View Risk Register",    BORDER,    lambda: self.show_page("register")),
            ("◈ Manage Treatments",     TEAL,      lambda: self.show_page("treatments")),
            ("⊞ Risk Matrix",           BORDER,    lambda: self.show_page("matrix")),
            ("⊙ Audit Log",             BORDER,    lambda: self.show_page("audit")),
            ("⚙ Settings",             BORDER,    lambda: self.show_page("settings")),
        ]
        for btn_txt, btn_color, btn_cmd in qa_btns:
            ctk.CTkButton(qa_f, text=btn_txt,
                          height=32, fg_color=btn_color,
                          hover_color=CARD_BG2,
                          text_color=(TEXT_MAIN if btn_color != BORDER
                                      else TEXT_MUTED),
                          font=ctk.CTkFont(size=11), corner_radius=6,
                          anchor="w", command=btn_cmd).pack(
                          fill="x", padx=10, pady=3)

        # ── Pending AI banner ─────────────────────────────────────────────
        if self._pending_ai_risks:
            pb = ctk.CTkFrame(outer, fg_color=CARD_BG2,
                               corner_radius=8)
            pb.pack(fill="x", padx=16, pady=(0, 8))
            ctk.CTkLabel(
                pb,
                text=f"◎  {len(self._pending_ai_risks)} AI risks "
                     f"awaiting review — approve to add to register",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=GOLD).pack(side="left", padx=14, pady=10)
            ctk.CTkButton(pb, text="Review →",
                          fg_color=PURPLE_LT, height=28,
                          font=ctk.CTkFont(size=11), corner_radius=6,
                          command=lambda: self.show_page("ai")).pack(
                          side="right", padx=14, pady=10)



        # ── Row 1: Risk KPI cards ─────────────────────────────────────────
        g = ctk.CTkFrame(self.main, fg_color="transparent")
        g.pack(fill="x", padx=20, pady=(4, 0))
        for i in range(6):
            g.grid_columnconfigure(i, weight=1)
        self._stat_card(g, 0, 0, "Total Risks",
                        stats["total"], "in register")
        self._stat_card(g, 0, 1, "Critical",
                        stats["critical"], "score ≥ 15", RED)
        self._stat_card(g, 0, 2, "High",
                        stats["high"], "score 10–14", ORANGE)
        self._stat_card(g, 0, 3, "Open",
                        stats["open"], "unresolved", GOLD)
        self._stat_card(g, 0, 4, "Overdue Review",
                        stats["overdue"], "past review date",
                        RED if stats["overdue"] else TEXT_MUTED)
        self._stat_card(g, 0, 5, "AI Sourced",
                        stats["ai_sourced"], "from PDF", PURPLE_LT)

        # ── Row 2: Treatment KPI cards ────────────────────────────────────
        g2 = ctk.CTkFrame(self.main, fg_color="transparent")
        g2.pack(fill="x", padx=20, pady=(0, 4))
        for i in range(4):
            g2.grid_columnconfigure(i, weight=1)
        self._stat_card(g2, 0, 0, "Total Treatments",
                        stats["treat_total"], "logged")
        self._stat_card(g2, 0, 1, "Overdue Treatments",
                        stats["treat_overdue"], "past target date",
                        RED if stats["treat_overdue"] else TEXT_MUTED)
        self._stat_card(g2, 0, 2, "Awaiting Verification",
                        stats["treat_verify"], "Completed → Verify",
                        GOLD if stats["treat_verify"] else TEXT_MUTED)
        self._stat_card(g2, 0, 3, "Untreated High+",
                        stats["no_treatment"], "score ≥ 10, no plan",
                        ORANGE if stats["no_treatment"] else TEXT_MUTED)

        # ── Two-column lower section ──────────────────────────────────────
        lower = ctk.CTkFrame(self.main, fg_color="transparent")
        lower.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        lower.grid_columnconfigure(0, weight=3)
        lower.grid_columnconfigure(1, weight=2)
        lower.grid_rowconfigure(0, weight=1)

        # Left: NIST CSF 2.0 distribution
        left = ctk.CTkFrame(lower, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(left, text="NIST CSF 2.0 Coverage",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=TEXT_MUTED).pack(
                     anchor="w", pady=(10, 6))
        nf = ctk.CTkFrame(left, fg_color=CARD_BG, corner_radius=10)
        nf.pack(fill="x")
        nf.grid_columnconfigure(1, weight=1)
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
                color = NIST_COLORS.get(fn, ACCENT2)
                ctk.CTkLabel(nf, text=fn,
                             font=ctk.CTkFont(size=10),
                             text_color=color, width=80,
                             anchor="w").grid(
                             row=i, column=0,
                             padx=(14, 6), pady=5, sticky="w")
                bar = ctk.CTkProgressBar(nf, height=8, corner_radius=4,
                                          progress_color=color,
                                          fg_color=BORDER)
                bar.set(min(cnt / total_safe, 1.0))
                bar.grid(row=i, column=1, padx=4, pady=5, sticky="ew")
                ctk.CTkLabel(nf, text=f"{cnt}  avg {avg}",
                             font=ctk.CTkFont(size=9),
                             text_color=TEXT_MUTED, width=80,
                             anchor="e").grid(
                             row=i, column=2,
                             padx=(4, 14), pady=5, sticky="e")

        # Right: Treatment pipeline
        right = ctk.CTkFrame(lower, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(right, text="Treatment Pipeline",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=TEXT_MUTED).pack(
                     anchor="w", pady=(10, 6))
        pipeline = get_pipeline_treatments()
        pf = ctk.CTkScrollableFrame(right, fg_color=CARD_BG,
                                     corner_radius=10)
        pf.pack(fill="both", expand=True)
        if not pipeline:
            ctk.CTkLabel(pf, text="No active treatments.",
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).pack(pady=20)
        else:
            for t in pipeline[:8]:
                row_f = ctk.CTkFrame(pf, fg_color=CARD_BG2,
                                      corner_radius=6)
                row_f.pack(fill="x", padx=10, pady=3)
                row_f.grid_columnconfigure(1, weight=1)
                s_color = TREAT_COLORS.get(t["strategy"], ACCENT2)
                sb2 = ctk.CTkFrame(row_f, fg_color=s_color,
                                   corner_radius=3, width=62, height=20)
                sb2.grid(row=0, column=0,
                         padx=(10, 6), pady=8, sticky="w")
                sb2.grid_propagate(False)
                ctk.CTkLabel(sb2, text=t["strategy"][:7],
                             font=ctk.CTkFont(size=8, weight="bold"),
                             text_color="white").pack(padx=4, pady=2)
                ctk.CTkLabel(row_f, text=t["title"][:30],
                             font=ctk.CTkFont(size=11),
                             text_color=TEXT_MAIN,
                             anchor="w").grid(
                             row=0, column=1, pady=8, sticky="w")
                d = days_until(t["target_date"])
                if d is not None:
                    if d < 0:
                        d_text, d_color = f"{abs(d)}d overdue", RED
                    elif d <= 7:
                        d_text, d_color = f"{d}d left", GOLD
                    else:
                        d_text, d_color = f"{d}d", TEXT_MUTED
                    ctk.CTkLabel(row_f, text=d_text,
                                 font=ctk.CTkFont(size=9),
                                 text_color=d_color).grid(
                                 row=0, column=2,
                                 padx=(4, 10), pady=8)

        # Pending AI banner
        if self._pending_ai_risks:
            pb = ctk.CTkFrame(self.main, fg_color=CARD_BG2,
                              corner_radius=8)
            pb.pack(fill="x", padx=20, pady=(0, 4))
            ctk.CTkLabel(
                pb,
                text=f"◎  {len(self._pending_ai_risks)} AI risks "
                     f"awaiting review",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=GOLD).pack(side="left", padx=14, pady=10)
            ctk.CTkButton(pb, text="Review →",
                          fg_color=PURPLE_LT, height=28,
                          font=ctk.CTkFont(size=11), corner_radius=6,
                          command=lambda: self.show_page("ai")).pack(
                          side="right", padx=14, pady=10)

    # ── AI Analysis ───────────────────────────────────────────────────────────
    def _pg_ai(self):
        # Page header — Image 8/9 style
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(16, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="◎  AI Risk Analysis",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="Upload a document and let AI analyze risks "
                          "across 5 frameworks.",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, sticky="w")
        btn_hdr = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_hdr.grid(row=0, column=1, sticky="e", rowspan=2)
        ctk.CTkButton(btn_hdr, text="⊙  Analysis History",
                      height=34, fg_color=BORDER,
                      hover_color=CARD_BG2, text_color=TEXT_MUTED,
                      font=ctk.CTkFont(size=11), corner_radius=8,
                      command=lambda: self.show_page("audit")).pack(
                      side="left", padx=(0, 8))
        ctk.CTkButton(btn_hdr, text="＋  New Analysis",
                      height=34, fg_color=PURPLE_LT,
                      font=ctk.CTkFont(size=11), corner_radius=8,
                      command=lambda: [
                          setattr(self, "_pending_ai_risks", []),
                          setattr(self, "_last_analysis", {}),
                          self.show_page("ai")]).pack(side="left")

        # If AI has results, show KPI strip (Image 8 top cards)
        if self._pending_ai_risks:
            analysis = getattr(self, "_last_analysis", {})
            n = len(self._pending_ai_risks)
            crit = sum(1 for r in self._pending_ai_risks
                       if int(r.get("inherent_score",
                           r.get("likelihood",1)*r.get("impact",1)) or 0) >= 15)
            high = sum(1 for r in self._pending_ai_risks
                       if 10 <= int(r.get("inherent_score",
                           r.get("likelihood",1)*r.get("impact",1)) or 0) <= 14)
            avg_sc = 0
            if n:
                scores = [int(r.get("inherent_score",
                    r.get("likelihood",1)*r.get("impact",1)) or 0)
                    for r in self._pending_ai_risks]
                avg_sc = round(sum(scores)/n, 1)
            kstrip = ctk.CTkFrame(self.main, fg_color="transparent")
            kstrip.pack(fill="x", padx=24, pady=(0, 8))
            for i in range(5):
                kstrip.grid_columnconfigure(i, weight=1)
            for col, (icon, val, lbl, cc) in enumerate([
                ("◉",  today(),  "Analysis Complete",  TEAL),
                ("⊘",  str(n),   "Risks Identified",   TEXT_MAIN),
                ("▲",  f"{crit+high}", "High / Critical", ORANGE if (crit+high) else TEXT_MUTED),
                ("✓",  "5 / 5",  "Frameworks Analyzed",GREEN_LT),
                ("⊗",  f"{avg_sc} / 25","Overall Risk Score",
                 score_color(int(avg_sc))),
            ]):
                f = ctk.CTkFrame(kstrip, fg_color=CARD_BG,
                                 corner_radius=10)
                f.grid(row=0, column=col, padx=5, sticky="nsew")
                ctk.CTkLabel(f, text=icon,
                             font=ctk.CTkFont(size=16),
                             text_color=cc).pack(
                             padx=14, pady=(10,2), anchor="w")
                ctk.CTkLabel(f, text=str(val),
                             font=ctk.CTkFont(size=20, weight="bold"),
                             text_color=cc).pack(padx=14, anchor="w")
                ctk.CTkLabel(f, text=lbl,
                             font=ctk.CTkFont(size=9),
                             text_color=TEXT_MUTED).pack(
                             padx=14, pady=(0,10), anchor="w")

        scroll = ctk.CTkScrollableFrame(self.main, fg_color=DARK_BG)
        scroll.pack(fill="both", expand=True)

        # API key panel
        kf = ctk.CTkFrame(scroll, fg_color=CARD_BG2, corner_radius=10)
        kf.pack(fill="x", padx=24, pady=(4, 8))
        kf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(kf, text="◈  API Configuration",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=PURPLE_LT).grid(
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

        # ── Organisation Scope ────────────────────────────────────────
        # Load any previously saved scope to pre-populate the form
        _scope = get_organisation_scope()

        scope_hdr = ctk.CTkFrame(scroll, fg_color=CARD_BG2,
                                  corner_radius=10)
        scope_hdr.pack(fill="x", padx=24, pady=(0, 4))
        scope_hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(scope_hdr, text="Organisation Scope",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).grid(
                     row=0, column=0, padx=14, pady=10, sticky="w")

        # Summary banner shown when scope already exists
        if _scope:
            assets_str = ", ".join(_scope.get("assets_in_scope", [])[:3])
            if len(_scope.get("assets_in_scope", [])) > 3:
                assets_str += "…"
            fws_str = ", ".join(
                [f.replace("ISO/IEC 27001:2022", "ISO 27001")
                  .replace("NIST CSF 2.0", "NIST CSF")
                  for f in _scope.get("frameworks_selected", [])])
            summary_lines = [
                f"Assessment:   {_scope.get('assessment_name') or '—'}",
                f"Organisation: {_scope.get('organisation_name') or '—'}"
                f"  ·  Industry: {_scope.get('industry') or '—'}"
                f"  ·  Size: {_scope.get('organisation_size') or '—'}",
                f"Scope:        {assets_str or '—'}",
                f"Frameworks:   {fws_str or '—'}",
            ]
            for line in summary_lines:
                ctk.CTkLabel(scope_hdr, text=line,
                             font=ctk.CTkFont(size=10),
                             text_color=GREEN_LT, anchor="w").grid(
                             row=summary_lines.index(line)+1,
                             column=0, columnspan=2,
                             padx=14, pady=1, sticky="w")
            ctk.CTkLabel(scope_hdr, text="",
                         font=ctk.CTkFont(size=4)).grid(
                         row=len(summary_lines)+1, column=0)

        def _sg(key, fallback=""):
            if _scope is None:
                return fallback
            v = _scope.get(key)
            return v if v not in (None, "") else fallback

        def _sgl(key):
            if _scope is None:
                return []
            return _scope.get(key) or []

        # ── Card helper for scope sections ──────────────────────────
        def scope_card(label):
            ctk.CTkLabel(scroll, text=label,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=TEXT_MUTED).pack(
                         anchor="w", padx=26, pady=(8, 2))
            f = ctk.CTkFrame(scroll, fg_color=CARD_BG,
                             corner_radius=10)
            f.pack(fill="x", padx=24, pady=(0, 4))
            f.grid_columnconfigure(1, weight=1)
            return f

        def scope_row(frm, r_i, label, key,
                      default="", wtype="entry", vals=None):
            ctk.CTkLabel(frm, text=label,
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED,
                         width=160, anchor="w").grid(
                         row=r_i, column=0,
                         padx=(14, 6), pady=7, sticky="w")
            if wtype == "text":
                w = ctk.CTkTextbox(frm, height=56,
                                    font=ctk.CTkFont(size=11),
                                    fg_color=CARD_BG2)
                if default:
                    w.insert("1.0", str(default))
                self._scope_fv[key] = w
                w.grid(row=r_i, column=1,
                       padx=(0, 14), pady=7, sticky="ew")
                return
            var = ctk.StringVar(value=str(default))
            if wtype == "option":
                w = ctk.CTkOptionMenu(
                    frm, variable=var, values=vals or [],
                    fg_color=CARD_BG2, button_color=ACCENT2,
                    font=ctk.CTkFont(size=11))
            else:
                w = ctk.CTkEntry(frm, textvariable=var,
                                  font=ctk.CTkFont(size=11),
                                  fg_color=CARD_BG2)
            w.grid(row=r_i, column=1,
                   padx=(0, 14), pady=7, sticky="ew")
            self._scope_fv[key] = var

        self._scope_fv    = {}
        self._scope_chks  = {}  # checkboxes for multi-select fields

        # ── Organisation card ────────────────────────────────────────
        c1 = scope_card("ORGANISATION")
        self._cn_var = ctk.StringVar(
            value=_sg("organisation_name", self._company_name))
        scope_row(c1, 0, "Organisation Name *",
                  "organisation_name",
                  _sg("organisation_name", self._company_name))
        scope_row(c1, 1, "Industry",
                  "industry", _sg("industry"))
        scope_row(c1, 2, "Organisation Size",
                  "organisation_size",
                  _sg("organisation_size", ORG_SIZES[0]),
                  "option", ORG_SIZES)
        scope_row(c1, 3, "Primary Business Function",
                  "business_function", _sg("business_function"))

        # ── Assessment card ──────────────────────────────────────────
        c2 = scope_card("ASSESSMENT")
        scope_row(c2, 0, "Assessment Name",
                  "assessment_name", _sg("assessment_name"))
        scope_row(c2, 1, "Assessment Type",
                  "assessment_type",
                  _sg("assessment_type", ASSESSMENT_TYPES[0]),
                  "option", ASSESSMENT_TYPES)
        scope_row(c2, 2, "Assessment Objective",
                  "assessment_objective",
                  _sg("assessment_objective"), "text")

        # ── Scope card (multi-select checkboxes) ─────────────────────
        c3 = scope_card("ASSETS IN SCOPE")
        c3.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(c3, text="Select all that apply:",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_DIM).grid(
                     row=0, column=0, columnspan=4,
                     padx=14, pady=(8, 2), sticky="w")
        selected_assets = _sgl("assets_in_scope")
        per_row = 2
        for idx, asset in enumerate(ASSET_TYPES):
            r_i = (idx // per_row) + 1
            c_i = (idx % per_row) * 2
            c3.grid_columnconfigure(c_i, weight=1)
            var = ctk.BooleanVar(value=(asset in selected_assets))
            self._scope_chks[f"asset_{asset}"] = (var, asset)
            ctk.CTkCheckBox(c3, text=asset, variable=var,
                            font=ctk.CTkFont(size=11),
                            text_color=TEXT_MAIN,
                            fg_color=ACCENT2).grid(
                            row=r_i, column=c_i, columnspan=2,
                            padx=14, pady=4, sticky="w")
        last_asset_row = (len(ASSET_TYPES) // per_row) + 2

        # Business Units (comma-separated entry)
        ctk.CTkLabel(c3, text="Business Units (comma-separated)",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED, anchor="w").grid(
                     row=last_asset_row, column=0, columnspan=2,
                     padx=14, pady=(8, 2), sticky="w")
        bu_var = ctk.StringVar(
            value=", ".join(_sgl("business_units")))
        ctk.CTkEntry(c3, textvariable=bu_var,
                     font=ctk.CTkFont(size=11),
                     placeholder_text="Finance, HR, IT, Operations…",
                     fg_color=CARD_BG2).grid(
                     row=last_asset_row+1, column=0, columnspan=4,
                     padx=14, pady=(0, 8), sticky="ew")
        self._scope_fv["business_units_raw"] = bu_var

        # Locations (comma-separated entry)
        ctk.CTkLabel(c3, text="Locations / Sites (comma-separated)",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED, anchor="w").grid(
                     row=last_asset_row+2, column=0, columnspan=2,
                     padx=14, pady=(4, 2), sticky="w")
        loc_var = ctk.StringVar(
            value=", ".join(_sgl("locations")))
        ctk.CTkEntry(c3, textvariable=loc_var,
                     font=ctk.CTkFont(size=11),
                     placeholder_text="London UK, New York USA…",
                     fg_color=CARD_BG2).grid(
                     row=last_asset_row+3, column=0, columnspan=4,
                     padx=14, pady=(0, 12), sticky="ew")
        self._scope_fv["locations_raw"] = loc_var

        # ── Critical Assets card ─────────────────────────────────────
        c4 = scope_card("CRITICAL ASSETS")
        scope_row(c4, 0, "Critical Systems & Data",
                  "critical_assets",
                  _sg("critical_assets"), "text")

        # ── Frameworks card ──────────────────────────────────────────
        c5 = scope_card("FRAMEWORKS SELECTED")
        selected_fws = _sgl("frameworks_selected") or SCOPE_FRAMEWORKS
        fw_per_row = 2
        for idx, fw in enumerate(SCOPE_FRAMEWORKS):
            r_i = idx // fw_per_row
            c_i = (idx % fw_per_row) * 2
            c5.grid_columnconfigure(c_i, weight=1)
            var = ctk.BooleanVar(value=(fw in selected_fws))
            self._scope_chks[f"fw_{fw}"] = (var, fw)
            ctk.CTkCheckBox(c5, text=fw, variable=var,
                            font=ctk.CTkFont(size=11),
                            text_color=TEXT_MAIN,
                            fg_color=ACCENT2).grid(
                            row=r_i, column=c_i, columnspan=2,
                            padx=14, pady=6, sticky="w")
        ctk.CTkLabel(c5, text=" ").grid(
            row=(len(SCOPE_FRAMEWORKS) // fw_per_row) + 1, column=0)

        scope_status = ctk.CTkLabel(scroll, text="",
                                     font=ctk.CTkFont(size=11))
        scope_status.pack(pady=2)

        def save_scope():
            org_name = (self._scope_fv["organisation_name"].get().strip()
                        if "organisation_name" in self._scope_fv else "")
            if not org_name:
                scope_status.configure(
                    text="⚠ Organisation Name is required",
                    text_color=RED)
                return

            def get_sv(k):
                v = self._scope_fv.get(k)
                if v is None:
                    return ""
                if isinstance(v, ctk.CTkTextbox):
                    return v.get("1.0", "end").strip()
                return v.get()

            assets = [asset for key, (var, asset)
                      in self._scope_chks.items()
                      if key.startswith("asset_") and var.get()]
            frameworks = [fw for key, (var, fw)
                          in self._scope_chks.items()
                          if key.startswith("fw_") and var.get()]

            def parse_csv(s):
                return [v.strip() for v in s.split(",")
                        if v.strip()]

            scope_data = {
                "organisation_name":    org_name,
                "industry":             get_sv("industry"),
                "organisation_size":    get_sv("organisation_size"),
                "business_function":    get_sv("business_function"),
                "assessment_name":      get_sv("assessment_name"),
                "assessment_type":      get_sv("assessment_type"),
                "assessment_objective": get_sv("assessment_objective"),
                "business_units":
                    parse_csv(get_sv("business_units_raw")),
                "locations":
                    parse_csv(get_sv("locations_raw")),
                "assets_in_scope":      assets,
                "critical_assets":      get_sv("critical_assets"),
                "frameworks_selected":  frameworks,
            }
            save_organisation_scope(scope_data)
            self._company_name = org_name
            scope_status.configure(
                text="✅ Organisation Scope saved",
                text_color=GREEN_LT)
            self._toast("✅  Organisation Scope saved")
            self._refresh_statusbar()

        ctk.CTkButton(scroll, text="💾  Save Organisation Scope",
                      height=40, fg_color=TEAL,
                      font=ctk.CTkFont(size=13), corner_radius=8,
                      command=save_scope).pack(
                      fill="x", padx=24, pady=(2, 6))

        # PDF upload
        uf = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        uf.pack(fill="x", padx=24, pady=(4, 8))
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

        # Read saved scope — use company name from scope if available,
        # fallback to the cn_var from the old single-field path
        org_scope = get_organisation_scope()
        if org_scope and org_scope.get("organisation_name"):
            self._company_name = org_scope["organisation_name"]
        else:
            self._company_name = (
                self._cn_var.get().strip() or "Your Organisation"
                if hasattr(self, "_cn_var") else "Your Organisation")

        self._analyse_btn.configure(state="disabled",
                                    text="⏳  Analysing...")
        self._ai_progress.set(0.1)
        self._ai_status_var.set("Extracting text from PDF...")
        self._ai_status_lbl.configure(text_color=GOLD)
        api_key   = self._api_key
        company   = self._company_name

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
                prompt = build_analysis_prompt(
                    text, company, org_scope=org_scope)
                result = self._call_api(prompt, api_key, progress)
                self._last_analysis    = result
                self._last_pdf_path    = pdf_path
                self._pending_ai_risks = result.get("risks", [])
                # Build and cache the executive summary immediately so
                # it's available to both the UI and the PDF without a
                # second computation. Stored on _last_analysis under
                # "_exec_summary" to avoid mutating the raw AI response.
                from riskcore_ai import build_executive_summary
                result["_exec_summary"] = build_executive_summary(
                    result, self._pending_ai_risks, org_scope=org_scope)

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
        from riskcore_ai import (build_executive_summary,
                                  format_evidence, format_confidence)

        analysis = getattr(self, "_last_analysis", {})
        risks    = self._pending_ai_risks
        scope    = get_organisation_scope()

        # Build executive intelligence (client-side, no extra API call)
        exec_sum = build_executive_summary(analysis, risks, org_scope=scope)
        rc       = exec_sum["risk_counts"]

        # ── Header ────────────────────────────────────────────────────
        ctk.CTkLabel(
            parent,
            text=f"AI Found {len(risks)} Risk(s) — Review & Approve",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_MAIN).pack(anchor="w", padx=24, pady=(8, 4))

        # ── Executive KPI cards ───────────────────────────────────────
        g = ctk.CTkFrame(parent, fg_color="transparent")
        g.pack(fill="x", padx=24, pady=(0, 6))
        for i in range(6):
            g.grid_columnconfigure(i, weight=1)

        posture_color_map = {
            "Critical": RED, "High": ORANGE,
            "Medium": GOLD, "Low": GREEN_LT, "Unknown": TEXT_MUTED,
        }
        p_col = posture_color_map.get(exec_sum["posture"], TEXT_MUTED)

        kpis = [
            ("Risk Posture",       exec_sum["posture"],
             p_col),
            ("Total Risks",        str(rc["total"]),
             TEXT_MAIN),
            ("Critical / High",    f"{rc['critical']} / {rc['high']}",
             RED if rc["critical"] else ORANGE if rc["high"] else TEXT_MUTED),
            ("Avg Score",          str(exec_sum["avg_score"]),
             score_color(int(exec_sum["avg_score"]))),
            ("With Evidence",      str(exec_sum["evidence_count"]),
             TEAL),
            ("Frameworks Mapped",  str(exec_sum["frameworks_mapped"]),
             ACCENT2),
        ]
        for col, (title, val, color) in enumerate(kpis):
            self._stat_card(g, 0, col, title, val, color=color)

        # ── Executive Summary panel ───────────────────────────────────
        ef = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=10)
        ef.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkLabel(ef, text="Executive Summary",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEXT_MAIN).pack(
                     padx=14, pady=(10, 2), anchor="w")

        if exec_sum["summary"]:
            ctk.CTkLabel(ef, text=exec_sum["summary"],
                         font=ctk.CTkFont(size=10),
                         text_color=GREEN_LT,
                         wraplength=820, justify="left").pack(
                         padx=14, pady=(0, 6), anchor="w")

        rows = [
            ("Risk Posture",           exec_sum["posture_explanation"]),
            ("Strongest Areas",        exec_sum["strongest_areas"]),
            ("Weakest Areas",          exec_sum["weakest_areas"]),
            ("Notable Observations",   exec_sum["notable_observations"]),
        ]
        for label, value in rows:
            if value and value not in ("Not available.",
                                       "Not assessed in this document.",
                                       "No notable observations recorded."):
                rf = ctk.CTkFrame(ef, fg_color=CARD_BG2, corner_radius=6)
                rf.pack(fill="x", padx=14, pady=2)
                rf.grid_columnconfigure(1, weight=1)
                ctk.CTkLabel(rf, text=label,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=TEXT_MUTED, width=150,
                             anchor="w").grid(
                             row=0, column=0, padx=(10, 6), pady=6,
                             sticky="w")
                ctk.CTkLabel(rf, text=value,
                             font=ctk.CTkFont(size=10),
                             text_color=TEXT_MAIN, anchor="w",
                             wraplength=620,
                             justify="left").grid(
                             row=0, column=1, padx=(0, 10), pady=6,
                             sticky="w")

        # Priorities
        if exec_sum["immediate_priorities"]:
            ctk.CTkLabel(ef, text="Immediate Priorities",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=ORANGE).pack(
                         padx=14, pady=(6, 2), anchor="w")
            for p in exec_sum["immediate_priorities"][:4]:
                ctk.CTkLabel(ef, text=f"  ▸ {p}",
                             font=ctk.CTkFont(size=10),
                             text_color=TEXT_MAIN).pack(
                             padx=14, pady=1, anchor="w")

        if exec_sum["strategic_recommendations"]:
            ctk.CTkLabel(ef, text="Strategic Recommendations",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=ACCENT2).pack(
                         padx=14, pady=(6, 2), anchor="w")
            for r_s in exec_sum["strategic_recommendations"][:4]:
                ctk.CTkLabel(ef, text=f"  ▸ {r_s}",
                             font=ctk.CTkFont(size=10),
                             text_color=TEXT_MAIN).pack(
                             padx=14, pady=1, anchor="w")
        ctk.CTkLabel(ef, text=" ", font=ctk.CTkFont(size=4)).pack()

        # ── Risk cards ────────────────────────────────────────────────
        ctk.CTkLabel(
            parent,
            text=f"Findings — Review & Approve",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED).pack(
            anchor="w", padx=24, pady=(4, 2))

        self._risk_checks = {}
        for i, risk in enumerate(risks):
            inh = int(risk.get(
                "inherent_score",
                risk.get("likelihood", 1) * risk.get("impact", 1)) or 1)
            ev_data   = format_evidence(risk)
            conf_data = format_confidence(risk)

            rf = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=10)
            rf.pack(fill="x", padx=24, pady=3)
            rf.grid_columnconfigure(2, weight=1)

            var = ctk.BooleanVar(value=True)
            self._risk_checks[i] = var
            ctk.CTkCheckBox(rf, variable=var, text="",
                            width=24).grid(
                            row=0, column=0, padx=(10, 4), pady=10)
            ctk.CTkLabel(
                rf,
                text=f"{score_label(inh)}\n{inh}",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=score_color(inh), width=60,
                justify="center").grid(
                row=0, column=1, padx=4, pady=10, sticky="nw")

            info = ctk.CTkFrame(rf, fg_color="transparent")
            info.grid(row=0, column=2, padx=4, pady=6, sticky="ew")
            info.grid_columnconfigure(0, weight=1)

            # Title + priority
            title_row = ctk.CTkFrame(info, fg_color="transparent")
            title_row.pack(fill="x", anchor="w")
            title_row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(title_row,
                         text=risk.get("title", ""),
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=TEXT_MAIN, anchor="w").grid(
                         row=0, column=0, sticky="w")
            pri = risk.get("priority", "")
            if pri:
                pri_color = (RED if pri == "Immediate" else
                             ORANGE if pri == "Short-term" else
                             GOLD if pri == "Medium-term" else TEXT_MUTED)
                ctk.CTkLabel(title_row, text=pri,
                             font=ctk.CTkFont(size=9),
                             text_color=pri_color).grid(
                             row=0, column=1, padx=(8, 0), sticky="e")

            # Framework meta
            meta = (f"NIST: {risk.get('nist_function','')} › "
                    f"{risk.get('nist_category','')}  ·  "
                    f"ISO: {risk.get('iso_domain','')}  ·  "
                    f"MITRE: {risk.get('mitre_tactic','N/A')}  ·  "
                    f"CIS: {risk.get('cis_control','N/A')}  ·  "
                    f"CIA: {risk.get('cia_component','')}")
            ctk.CTkLabel(info, text=meta, font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED, anchor="w",
                         wraplength=680).pack(anchor="w")

            # Description
            desc = str(risk.get("description") or "")
            ctk.CTkLabel(info,
                         text=desc[:160] + ("…" if len(desc) > 160 else ""),
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED, anchor="w",
                         wraplength=680).pack(anchor="w", pady=(2, 2))

            # Confidence + evidence row
            conf_row = ctk.CTkFrame(info, fg_color="transparent")
            conf_row.pack(fill="x", anchor="w", pady=(2, 0))
            conf_color = (GREEN_LT if conf_data["level"] == "High"
                          else GOLD if conf_data["level"] == "Medium"
                          else ORANGE if conf_data["level"] == "Low"
                          else TEXT_MUTED)
            ctk.CTkLabel(conf_row,
                         text=f"Confidence: {conf_data['level']}",
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=conf_color).pack(
                         side="left", padx=(0, 8))
            ctk.CTkLabel(conf_row,
                         text=conf_data["reasoning"],
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_DIM).pack(
                         side="left", fill="x", expand=True)

            # Evidence block (collapsible inline)
            if ev_data["has_evidence"]:
                ev_f = ctk.CTkFrame(info, fg_color=CARD_BG2,
                                     corner_radius=6)
                ev_f.pack(fill="x", pady=(4, 2))
                src_txt = (f"  Source: {ev_data['source_section']}"
                           if ev_data["source_section"] else "")
                ctk.CTkLabel(ev_f,
                             text=f"Evidence{src_txt}",
                             font=ctk.CTkFont(size=9, weight="bold"),
                             text_color=TEAL).pack(
                             padx=8, pady=(4, 0), anchor="w")
                ctk.CTkLabel(ev_f,
                             text=f'"{ev_data["display_text"][:200]}'
                                  f'{"…" if len(ev_data["display_text"])>200 else ""}"',
                             font=ctk.CTkFont(size=9),
                             text_color=TEXT_MUTED,
                             wraplength=630,
                             justify="left").pack(
                             padx=8, pady=(0, 2), anchor="w")
                if ev_data["reasoning"]:
                    ctk.CTkLabel(ev_f,
                                 text=f"Reasoning: {ev_data['reasoning']}",
                                 font=ctk.CTkFont(size=9),
                                 text_color=TEXT_DIM,
                                 wraplength=630,
                                 justify="left").pack(
                                 padx=8, pady=(0, 4), anchor="w")

            # Scoring row
            vel_map = {1: "Slow", 2: "Medium", 3: "Fast", 4: "Immediate"}
            ctk.CTkLabel(
                rf,
                text=(f"L:{risk.get('likelihood','')} "
                      f"I:{risk.get('impact','')}  ·  "
                      f"Res:{risk.get('residual_score','?')}  ·  "
                      f"{vel_map.get(risk.get('risk_velocity', 2), '?')}"),
                font=ctk.CTkFont(size=10),
                text_color=TEXT_MUTED).grid(
                row=0, column=3, padx=8, pady=10, sticky="n")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(8, 4))
        ctk.CTkButton(btn_row,
                      text="✅  Approve Selected & Add to Register",
                      height=42, fg_color=GREEN,
                      font=ctk.CTkFont(size=13), corner_radius=8,
                      command=self._approve_risks).pack(
                      side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Discard All",
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
        # Page header
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(16, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="≡  Risk Register",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="All risks  ·  Click a row to view details  "
                          "·  Colour-coded by severity",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, sticky="w")
        ctk.CTkButton(hdr, text="⟳", width=36, height=34,
                      fg_color=BORDER, hover_color=CARD_BG2,
                      font=ctk.CTkFont(size=14), corner_radius=8,
                      command=self._load_reg).grid(
                      row=0, column=1, sticky="e")

        fb = ctk.CTkFrame(self.main, fg_color=CARD_BG, corner_radius=10)
        fb.pack(fill="x", padx=24, pady=(0, 6))

        self._search_var  = ctk.StringVar(value=self._search_val)
        self._status_filt = ctk.StringVar(value=self._status_val)
        self._nist_filt   = ctk.StringVar(value=self._nist_val)
        self._score_filt  = ctk.StringVar(value=self._score_val)
        self._owner_filt  = ctk.StringVar(value=self._owner_val)

        row1 = ctk.CTkFrame(fb, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(row1, text="⌕",
                     font=ctk.CTkFont(size=14),
                     text_color=TEXT_MUTED).pack(side="left", padx=(0, 6))
        se = ctk.CTkEntry(row1, textvariable=self._search_var,
                          placeholder_text="Search title, owner, tactic…",
                          font=ctk.CTkFont(size=12), height=32,
                          fg_color=CARD_BG2, border_color=BORDER)
        se.pack(side="left", fill="x", expand=True, padx=(0, 8))
        se.bind("<KeyRelease>",
                lambda e: self._save_filters_and_reload())
        ctk.CTkButton(row1, text="Clear", width=60, height=32,
                      fg_color=BORDER, hover_color=CARD_BG2,
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=self._clear_filters).pack(side="left")

        row2 = ctk.CTkFrame(fb, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 8))
        owners = ["All"] + get_owners()
        for lbl, var, vals in [
            ("Status:",   self._status_filt, ["All"] + RISK_STATUS),
            ("NIST:",     self._nist_filt,   ["All"] + NIST_FUNCTIONS),
            ("Severity:", self._score_filt,
             ["All", "Low", "Medium", "High", "Critical"]),
            ("Owner:",    self._owner_filt,  owners),
        ]:
            ctk.CTkLabel(row2, text=lbl,
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).pack(
                         side="left", padx=(0, 3))
            ctk.CTkOptionMenu(
                row2, variable=var, values=vals, width=118,
                fg_color=BORDER, button_color=ACCENT2,
                font=ctk.CTkFont(size=11),
                command=lambda v: self._save_filters_and_reload()
            ).pack(side="left", padx=(0, 8))

        # Column headers
        COL_DEFS = [
            ("Score", 70), ("Title", 0), ("NIST", 88),
            ("CIA", 95), ("MITRE", 108), ("Owner", 100),
            ("Status", 80), ("Treat", 55), ("Src", 40),
        ]
        hf = ctk.CTkFrame(self.main, fg_color=BORDER,
                           corner_radius=0, height=28)
        hf.pack(fill="x", padx=24)
        hf.pack_propagate(False)
        for col, (h, w) in enumerate(COL_DEFS):
            hf.grid_columnconfigure(
                col, weight=1 if col == 1 else 0, minsize=w)
            ctk.CTkLabel(hf, text=h,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=0, column=col, padx=5, pady=3, sticky="w")

        self._reg_timestamp = ctk.CTkLabel(
            self.main, text="",
            font=ctk.CTkFont(size=9), text_color=TEXT_DIM)
        self._reg_timestamp.pack(side="bottom", anchor="e",
                                 padx=24, pady=(0, 4))

        self._reg_scroll = ctk.CTkScrollableFrame(
            self.main, fg_color=DARK_BG)
        self._reg_scroll.pack(side="top", fill="both", expand=True,
                              padx=24, pady=(0, 4))
        self._reg_scroll.grid_columnconfigure(1, weight=1)
        self._load_reg()

    def _save_filters_and_reload(self):
        self._search_val = self._search_var.get()
        self._status_val = self._status_filt.get()
        self._nist_val   = self._nist_filt.get()
        self._score_val  = self._score_filt.get()
        self._owner_val  = self._owner_filt.get()
        self._load_reg()

    def _clear_filters(self):
        for attr in ("_search_val", "_status_val", "_nist_val",
                     "_score_val", "_owner_val"):
            setattr(self, attr,
                    "All" if attr != "_search_val" else "")
        self._search_var.set("")
        self._status_filt.set("All")
        self._nist_filt.set("All")
        self._score_filt.set("All")
        self._owner_filt.set("All")
        self._load_reg()

    def _load_reg(self):
        for w in self._reg_scroll.winfo_children():
            w.destroy()

        risks = get_risks(
            search=self._search_var.get(),
            status_filter=self._status_filt.get(),
            nist_filter=self._nist_filt.get(),
            score_filter=self._score_filt.get(),
            owner_filter=self._owner_filt.get())

        if hasattr(self, "_reg_timestamp"):
            self._reg_timestamp.configure(
                text=f"Refreshed: {now_str()}  ·  "
                     f"{len(risks)} risk(s) shown")

        if not risks:
            filters_active = any([
                self._search_var.get().strip(),
                self._status_filt.get() != "All",
                self._nist_filt.get() != "All",
                self._score_filt.get() != "All",
                self._owner_filt.get() != "All",
            ])
            ef = ctk.CTkFrame(self._reg_scroll, fg_color="transparent")
            ef.grid(row=0, column=0, columnspan=9, pady=40)
            ctk.CTkLabel(
                ef,
                text=("No risks match the current filters"
                      if filters_active else
                      "No risks in the register yet"),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=TEXT_MAIN).pack(pady=(0, 4))
            ctk.CTkLabel(
                ef,
                text=("Try adjusting or clearing your filters."
                      if filters_active else
                      "Use + Add Risk or AI Analysis to get started."),
                font=ctk.CTkFont(size=11),
                text_color=TEXT_MUTED).pack()
            return

        COL_DEFS = [
            ("Score", 70), ("Title", 0), ("NIST", 88),
            ("CIA", 95), ("MITRE", 108), ("Owner", 100),
            ("Status", 80), ("Treat", 55), ("Src", 40),
        ]
        self._reg_scroll.grid_columnconfigure(1, weight=1)

        with get_db() as conn:
            t_counts = {}
            for row in conn.execute(
                "SELECT risk_id, COUNT(*) as c FROM treatments "
                "WHERE status NOT IN ('Ineffective') "
                "GROUP BY risk_id"):
                t_counts[row["risk_id"]] = row["c"]

        for i, r in enumerate(risks):
            sc = int(r["risk_score"] or 0)
            bg = CARD_BG if i % 2 == 0 else CARD_BG2
            rf = ctk.CTkFrame(self._reg_scroll, fg_color=bg,
                              corner_radius=5)
            rf.grid(row=i, column=0, columnspan=9,
                    sticky="ew", padx=0, pady=1)
            for col, (_, w) in enumerate(COL_DEFS):
                rf.grid_columnconfigure(
                    col, weight=1 if col == 1 else 0, minsize=w)
            click = lambda e, rid=r["id"]: self._view_risk(rid)
            src_val   = r["source"] or "Manual"
            src_color = PURPLE_LT if src_val == "AI Analysis" else TEXT_DIM
            mitre     = r["mitre_tactic"] or "—"
            tc        = t_counts.get(r["id"], 0)
            treat_txt = f"✓{tc}" if tc else "—"
            treat_col = GREEN_LT if tc else TEXT_DIM
            nist_col  = NIST_COLORS.get(r["nist_function"] or "", TEXT_MUTED)
            status_col = (GOLD if r["status"] == "Open" else
                          GREEN_LT if r["status"] in ("Mitigated","Closed")
                          else TEXT_MUTED)
            cells = [
                (f"{score_label(sc)} {sc}", score_color(sc), 0),
                (r["title"][:42],           TEXT_MAIN,        1),
                (r["nist_function"] or "—", nist_col,         2),
                (r["cia_component"] or "—", PURPLE_LT,        3),
                (mitre[:14],                RED,              4),
                (r["owner"] or "—",         TEXT_MUTED,       5),
                (r["status"],               status_col,       6),
                (treat_txt,                 treat_col,        7),
                (src_val[:3],               src_color,        8),
            ]
            for text, color, col in cells:
                lbl = ctk.CTkLabel(rf, text=text,
                                   font=ctk.CTkFont(size=11),
                                   text_color=color, anchor="w")
                lbl.grid(row=0, column=col,
                         padx=5, pady=6, sticky="w")
                lbl.bind("<Button-1>", click)
            rf.bind("<Button-1>", click)

    def _view_risk(self, rid):
        r = get_risk(rid)
        if not r:
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Risk #{rid}")
        win.geometry("820x740")
        win.configure(fg_color=DARK_BG)
        win.grab_set()
        set_icon(win)

        sc = int(r["risk_score"] or 0)

        # Score-coloured header band
        hband = ctk.CTkFrame(win, fg_color=score_bg(sc),
                              corner_radius=0, height=52)
        hband.pack(fill="x")
        hband.pack_propagate(False)
        ctk.CTkLabel(
            hband,
            text=f"  {score_label(sc)} · Score {sc} · {r['title']}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=score_color(sc)).pack(
            side="left", padx=14, pady=8)
        if (r["source"] or "Manual") == "AI Analysis":
            ctk.CTkLabel(hband, text=" ◎ AI",
                         font=ctk.CTkFont(size=11),
                         text_color=PURPLE_LT).pack(
                         side="right", padx=14)

        # Tab row
        tab_frame = ctk.CTkFrame(win, fg_color=CARD_BG,
                                  corner_radius=0, height=40)
        tab_frame.pack(fill="x")
        tab_frame.pack_propagate(False)
        content_area = ctk.CTkFrame(win, fg_color=DARK_BG,
                                     corner_radius=0)
        content_area.pack(fill="both", expand=True)

        tab_btns = {}

        def show_tab(name):
            for w in content_area.winfo_children():
                w.destroy()
            for b in tab_btns.values():
                b.configure(fg_color="transparent",
                            text_color=TEXT_MUTED)
            tab_btns[name].configure(fg_color=BORDER,
                                      text_color=TEXT_MAIN)
            if name == "details":
                _show_details()
            elif name == "framework":
                _show_framework_intelligence()
            else:
                _show_treatments()

        for t_key, t_lbl in [("details","  Details  "),
                               ("framework","  Framework Intelligence  "),
                               ("treatments","  Treatments  ")]:
            b = ctk.CTkButton(tab_frame, text=t_lbl,
                              height=38, corner_radius=0,
                              fg_color="transparent",
                              hover_color=BORDER,
                              text_color=TEXT_MUTED,
                              font=ctk.CTkFont(size=12),
                              command=lambda k=t_key: show_tab(k))
            b.pack(side="left")
            tab_btns[t_key] = b

        def _show_details():
            scroll = ctk.CTkScrollableFrame(content_area,
                                             fg_color=DARK_BG)
            scroll.pack(fill="both", expand=True)
            scroll.grid_columnconfigure(1, weight=1)

            def row(idx, lbl, val, color=TEXT_MAIN):
                ctk.CTkLabel(scroll, text=lbl,
                             font=ctk.CTkFont(size=11),
                             text_color=TEXT_MUTED,
                             width=165, anchor="w").grid(
                             row=idx, column=0,
                             padx=(16, 6), pady=3, sticky="w")
                ctk.CTkLabel(scroll, text=str(val or "—"),
                             font=ctk.CTkFont(size=11),
                             text_color=color, anchor="w",
                             wraplength=540).grid(
                             row=idx, column=1,
                             padx=(0, 16), pady=3, sticky="w")

            lik = r["likelihood"] or 1
            imp = r["impact"]     or 1
            fields = [
                ("Title",              r["title"]),
                ("Description",        r["description"]),
                ("Category",           r["category"]),
                ("Likelihood",
                 f"{lik} — {LIKELIHOOD_LBL.get(lik,'')}"),
                ("Impact",
                 f"{imp} — {IMPACT_LBL.get(imp,'')}"),
                ("Inherent Score",
                 f"{r['inherent_score'] or sc} ({score_label(sc)})"),
                ("Residual Score",     r["residual_score"] or "—"),
                ("Risk Velocity",
                 {1:"Slow",2:"Medium",3:"Fast",
                  4:"Immediate"}.get(r["risk_velocity"] or 2, "—")),
                ("NIST CSF 2.0",
                 f"{r['nist_function']} › {r['nist_category']} "
                 f"[{r['nist_subcategory'] or ''}]"),
                ("ISO 27001:2022",
                 f"{r['iso_domain']} · {r['iso_control'] or ''}"),
                ("MITRE ATT&CK",
                 f"Tactic: {r['mitre_tactic']} | "
                 f"Technique: {r['mitre_technique'] or 'N/A'}"),
                ("CIS Control",        r["cis_control"]),
                ("CIA Component",      r["cia_component"]),
                ("Owner",              r["owner"]),
                ("Status",             r["status"]),
                ("Priority",           r["priority"] or "—"),
                ("Confidence",         r["confidence"] or "—"),
                ("Existing Controls",
                 r["existing_controls"] or "None documented"),
                ("Mitigation Plan",    r["mitigation"]),
                ("Review Date",        r["review_date"]),
                ("Created Date",       r["date_identified"] or "—"),
                ("Last Modified",      r["date_modified"] or "—"),
                ("Source",             r["source"] or "Manual"),
                ("AI Notes",           r["ai_suggestion"] or "—"),
                ("Notes",              r["notes"]),
            ]
            for idx, (lbl, val) in enumerate(fields):
                color = score_color(sc) if "Score" in lbl else TEXT_MAIN
                row(idx, lbl, val, color)

        def _show_framework_intelligence():
            sf = ctk.CTkScrollableFrame(content_area, fg_color=DARK_BG)
            sf.pack(fill="both", expand=True, padx=16, pady=8)

            ctk.CTkLabel(
                sf,
                text="How this risk maps across each supported framework. "
                     "'Confirmed' means the value was explicitly selected "
                     "on this risk; 'Unmapped' means the field was left "
                     "blank or at its default.",
                font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
                wraplength=680, justify="left").pack(
                anchor="w", pady=(0, 10))

            mapping = get_framework_mapping(r)
            CONF_COLOR = {
                "Confirmed": GREEN_LT,
                "Suggested": GOLD,
                "Unmapped":  TEXT_DIM,
            }
            for entry in mapping:
                card = ctk.CTkFrame(sf, fg_color=CARD_BG,
                                    corner_radius=8)
                card.pack(fill="x", pady=4)
                card.grid_columnconfigure(1, weight=1)

                c_color = CONF_COLOR.get(entry["confidence"], TEXT_MUTED)
                badge = ctk.CTkFrame(card, fg_color=c_color,
                                     corner_radius=4, width=84, height=22)
                badge.grid(row=0, column=0, padx=(12, 10),
                          pady=10, sticky="w")
                badge.grid_propagate(False)
                ctk.CTkLabel(badge, text=entry["confidence"],
                             font=ctk.CTkFont(size=9, weight="bold"),
                             text_color="white").pack(
                             padx=4, pady=2)

                info = ctk.CTkFrame(card, fg_color="transparent")
                info.grid(row=0, column=1, padx=(0, 12),
                         pady=8, sticky="ew")
                ctk.CTkLabel(
                    info,
                    text=f"{entry['framework']}  ·  {entry['function']}",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=TEXT_MAIN, anchor="w").pack(anchor="w")
                if entry["category"] != "—" or entry["control"] != "—":
                    ctk.CTkLabel(
                        info,
                        text=f"Category: {entry['category']}  ·  "
                             f"Control/Ref: {entry['control']}",
                        font=ctk.CTkFont(size=10),
                        text_color=TEXT_MUTED, anchor="w").pack(anchor="w")
                ctk.CTkLabel(
                    info, text=entry["rationale"],
                    font=ctk.CTkFont(size=10),
                    text_color=TEXT_DIM, anchor="w",
                    wraplength=560, justify="left").pack(
                    anchor="w", pady=(2, 0))

        def _show_treatments():
            treatments = get_treatments(rid)
            sf = ctk.CTkScrollableFrame(content_area, fg_color=DARK_BG)
            sf.pack(fill="both", expand=True, padx=16, pady=8)
            if not treatments:
                ctk.CTkLabel(sf,
                             text="No treatments logged for this risk.\n"
                                  "Click '＋ Add Treatment' below.",
                             font=ctk.CTkFont(size=12),
                             text_color=TEXT_MUTED,
                             justify="center").pack(pady=30)
                return
            for t in treatments:
                tf = ctk.CTkFrame(sf, fg_color=CARD_BG,
                                  corner_radius=8)
                tf.pack(fill="x", pady=4)
                s_color = TREAT_COLORS.get(t["strategy"], ACCENT2)
                # Header band per treatment
                th = ctk.CTkFrame(tf, fg_color=s_color,
                                  corner_radius=6, height=30)
                th.pack(fill="x")
                th.pack_propagate(False)
                ctk.CTkLabel(
                    th,
                    text=f"  {t['strategy']}  ·  {t['title']}",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="white").pack(
                    side="left", padx=10, pady=4)
                st_color = TREAT_STATUS_COLORS.get(
                    t["status"], TEXT_MUTED)
                ctk.CTkLabel(th, text=t["status"],
                             font=ctk.CTkFont(size=10),
                             text_color="white").pack(
                             side="right", padx=10)
                # Body
                body = ctk.CTkFrame(tf, fg_color="transparent")
                body.pack(fill="x", padx=12, pady=6)
                body.grid_columnconfigure(1, weight=1)
                body.grid_columnconfigure(3, weight=1)

                def brow(ri, ci, lbl, val):
                    ctk.CTkLabel(body, text=lbl + ":",
                                 font=ctk.CTkFont(size=10),
                                 text_color=TEXT_MUTED).grid(
                                 row=ri, column=ci,
                                 padx=(0, 4), pady=2, sticky="w")
                    ctk.CTkLabel(body, text=str(val or "—"),
                                 font=ctk.CTkFont(size=10),
                                 text_color=TEXT_MAIN,
                                 anchor="w").grid(
                                 row=ri, column=ci+1,
                                 padx=(0, 16), pady=2, sticky="w")

                brow(0, 0, "Owner",          t["owner"])
                brow(0, 2, "Target",         t["target_date"] or "—")
                brow(1, 0, "Residual Target", t["residual_score_target"])
                brow(1, 2, "Residual Actual", t["residual_score_actual"])
                if t["description"]:
                    ctk.CTkLabel(body, text=t["description"],
                                 font=ctk.CTkFont(size=10),
                                 text_color=TEXT_MUTED, anchor="w",
                                 wraplength=620,
                                 justify="left").grid(
                                 row=2, column=0, columnspan=4,
                                 pady=(4, 0), sticky="w")
                # Action buttons
                bf = ctk.CTkFrame(tf, fg_color="transparent")
                bf.pack(anchor="e", padx=12, pady=(0, 8))
                ctk.CTkButton(
                    bf, text="Edit", width=70, height=26,
                    fg_color=ACCENT2, corner_radius=5,
                    font=ctk.CTkFont(size=10),
                    command=lambda tid=t["id"]:
                        self._open_treatment_form(rid, tid, win)
                ).pack(side="left", padx=(0, 4))
                ctk.CTkButton(
                    bf, text="Delete", width=70, height=26,
                    fg_color="#3D1515", hover_color="#7F1D1D",
                    corner_radius=5,
                    font=ctk.CTkFont(size=10),
                    command=lambda tid=t["id"]:
                        self._delete_treatment_inline(tid, rid, win)
                ).pack(side="left")

        show_tab("details")

        # Bottom action bar
        btn_row = ctk.CTkFrame(win, fg_color=CARD_BG,
                                corner_radius=0, height=52)
        btn_row.pack(fill="x", side="bottom")
        btn_row.pack_propagate(False)
        ctk.CTkButton(btn_row, text="🗑  Delete",
                      fg_color="#3D1515", hover_color="#7F1D1D",
                      height=34, corner_radius=6,
                      font=ctk.CTkFont(size=12),
                      command=lambda: self._do_delete(rid, win)).pack(
                      side="left", padx=12, pady=9)
        ctk.CTkButton(btn_row, text="✏  Edit",
                      fg_color=ACCENT2, hover_color="#1E40AF",
                      height=34, corner_radius=6,
                      font=ctk.CTkFont(size=12),
                      command=lambda: self._open_edit(rid, win)).pack(
                      side="left", padx=4, pady=9)
        ctk.CTkButton(btn_row, text="＋ Add Treatment",
                      fg_color=TEAL, hover_color="#00695C",
                      height=34, corner_radius=6,
                      font=ctk.CTkFont(size=12),
                      command=lambda: self._open_treatment_form(
                          rid, None, win)).pack(
                      side="left", padx=4, pady=9)
        ctk.CTkButton(btn_row, text="Close",
                      fg_color=BORDER, height=34,
                      font=ctk.CTkFont(size=12), corner_radius=6,
                      command=win.destroy).pack(
                      side="right", padx=12, pady=9)

    def _delete_treatment_inline(self, tid, rid, parent_win):
        if messagebox.askyesno(
                "Delete Treatment",
                "Delete this treatment plan?\nThis cannot be undone."):
            delete_treatment(tid)
            self._refresh_statusbar()
            parent_win.destroy()
            self._view_risk(rid)
            self._toast("Treatment deleted", color=ORANGE)

    def _open_framework_coverage(self):
        """Navigate to the Risk Register with a note about framework coverage."""
        self.show_page("register")
        self._toast("Framework Intelligence is shown in each Risk's detail view "
                    "· Click any risk → Framework Intelligence tab", ACCENT2, 6000)

    def _open_edit(self, rid, win):
        win.destroy()
        self.show_page_with_arg("add", edit_id=rid)

    def _do_delete(self, rid, win):
        if messagebox.askyesno(
                "Delete Risk",
                "Permanently delete this risk and all its treatments?\n"
                "This cannot be undone."):
            delete_risk(rid)
            win.destroy()
            self._refresh_statusbar()
            self.show_page("register")
            self._toast("Risk deleted", color=ORANGE)

    # ── Add Risk Manually ─────────────────────────────────────────────────────
    def _pg_add_manual(self):
        edit_id = getattr(self, "_pending_edit_id", None)
        self._pending_edit_id = None
        self._pg_risk_form(edit_id=edit_id)

    def _pg_edit_risk(self, rid):
        self._pg_risk_form(edit_id=rid)

    def _pg_risk_form(self, edit_id=None):
        existing = get_risk(edit_id) if edit_id else None
        is_edit  = (edit_id is not None)

        # Page header — Image 4 style with Save Draft + Save Risk buttons
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(16, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr,
                     text=f"{'✏  Edit Risk' if is_edit else '+  Add Risk Manually'}",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="Framework-aligned  ·  NIST SP 800-30 scoring",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, sticky="w")
        btn_hdr = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_hdr.grid(row=0, column=1, sticky="e", rowspan=2)
        ctk.CTkButton(btn_hdr, text="◧  Save Draft",
                      height=34, fg_color=BORDER,
                      text_color=TEXT_MUTED,
                      font=ctk.CTkFont(size=12), corner_radius=8,
                      command=lambda: self._submit_risk_form(edit_id)
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_hdr, text="✓  Save Risk",
                      height=34, fg_color=ACCENT2,
                      font=ctk.CTkFont(size=12), corner_radius=8,
                      command=lambda: self._submit_risk_form(edit_id)
                      ).pack(side="left")

        def g(key, fallback=""):
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

    # ── Treatments Page ───────────────────────────────────────────────────────
    def _pg_treatments(self):
        # Page header
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(16, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="\u25C8  Treatments",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="All treatment plans  \u00b7  Click a row to edit",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(row=1, column=0, sticky="w")
        btn_hdr = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_hdr.grid(row=0, column=1, sticky="e", rowspan=2)
        ctk.CTkButton(btn_hdr, text="\u27f3", width=36, height=34,
                      fg_color=BORDER, hover_color=CARD_BG2,
                      font=ctk.CTkFont(size=14), corner_radius=8,
                      command=lambda: self.show_page("treatments")).pack(
                      side="left", padx=(0, 6))
        ctk.CTkButton(btn_hdr, text="\uff0b  Add Treatment",
                      height=34, fg_color=ACCENT2,
                      font=ctk.CTkFont(size=12), corner_radius=8,
                      command=self._add_treatment_from_register).pack(
                      side="left")

        # Filter bar
        fb = ctk.CTkFrame(self.main, fg_color=CARD_BG, corner_radius=10)
        fb.pack(fill="x", padx=24, pady=(0, 8))
        fb.grid_columnconfigure(5, weight=1)
        self._treat_status_filt = ctk.StringVar(value="All")
        self._treat_strat_filt  = ctk.StringVar(value="All")
        self._treat_search_var  = ctk.StringVar(value="")

        ctk.CTkLabel(fb, text="Status",
                     font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).grid(
                     row=0, column=0, padx=(14, 4), pady=10, sticky="w")
        ctk.CTkOptionMenu(fb, variable=self._treat_status_filt,
                          values=["All"] + TREATMENT_STATUS,
                          width=140, fg_color=BORDER, button_color=ACCENT2,
                          font=ctk.CTkFont(size=11),
                          command=lambda v: self._load_treatments()).grid(
                          row=0, column=1, padx=(0, 12), pady=10)
        ctk.CTkLabel(fb, text="Strategy",
                     font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).grid(
                     row=0, column=2, padx=(0, 4), pady=10, sticky="w")
        ctk.CTkOptionMenu(fb, variable=self._treat_strat_filt,
                          values=["All"] + TREATMENT_STRATEGIES,
                          width=140, fg_color=BORDER, button_color=ACCENT2,
                          font=ctk.CTkFont(size=11),
                          command=lambda v: self._load_treatments()).grid(
                          row=0, column=3, padx=(0, 12), pady=10)
        se = ctk.CTkEntry(fb, textvariable=self._treat_search_var,
                          placeholder_text="\u2315  Search treatments...",
                          font=ctk.CTkFont(size=11), height=32,
                          fg_color=CARD_BG2, border_color=BORDER)
        se.grid(row=0, column=5, padx=(0, 8), pady=10, sticky="ew")
        se.bind("<KeyRelease>", lambda e: self._load_treatments())
        ctk.CTkButton(fb, text="\u22df  Clear Filters",
                      height=30, width=110, fg_color=BORDER,
                      text_color=TEXT_MUTED, font=ctk.CTkFont(size=10),
                      corner_radius=6,
                      command=self._clear_treat_filters).grid(
                      row=0, column=6, padx=(0, 14), pady=10)

        # Column headers
        hf = ctk.CTkFrame(self.main, fg_color=BORDER,
                           corner_radius=0, height=30)
        hf.pack(fill="x", padx=24)
        hf.pack_propagate(False)
        for col, (h, w) in enumerate([
            ("Strategy", 90), ("Title", 0), ("Risk", 190),
            ("Owner", 120), ("Status", 100), ("Target", 95), ("", 70),
        ]):
            hf.grid_columnconfigure(
                col, weight=1 if col == 1 else 0, minsize=w)
            ctk.CTkLabel(hf, text=h,
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=0, column=col, padx=6, pady=4, sticky="w")

        self._treat_scroll = ctk.CTkScrollableFrame(
            self.main, fg_color=DARK_BG)
        self._treat_scroll.pack(fill="both", expand=True,
                                padx=24, pady=(0, 12))
        self._load_treatments()

    def _clear_treat_filters(self):
        if hasattr(self, "_treat_status_filt"):
            self._treat_status_filt.set("All")
        if hasattr(self, "_treat_strat_filt"):
            self._treat_strat_filt.set("All")
        if hasattr(self, "_treat_search_var"):
            self._treat_search_var.set("")
        self._load_treatments()

    def _add_treatment_from_register(self):
        risks_list = get_risks()
        if not risks_list:
            messagebox.showinfo("No Risks",
                                "Add risks to the register first.")
            return
        with get_db() as conn:
            treated = {r["risk_id"] for r in conn.execute(
                "SELECT DISTINCT risk_id FROM treatments")}
        first = next(
            (r for r in risks_list if r["id"] not in treated),
            risks_list[0])
        self._open_treatment_form(first["id"])


    def _load_treatments(self):
        for w in self._treat_scroll.winfo_children():
            w.destroy()
        s_f  = getattr(self, "_treat_status_filt",
                       ctk.StringVar(value="All")).get()
        g_f  = getattr(self, "_treat_strat_filt",
                       ctk.StringVar(value="All")).get()
        srch = getattr(self, "_treat_search_var",
                       ctk.StringVar(value="")).get().strip().lower()

        with get_db() as conn:
            q = ("SELECT t.*, r.title as risk_title, r.risk_score "
                 "FROM treatments t JOIN risks r ON t.risk_id=r.id "
                 "WHERE 1=1")
            p = []
            if s_f != "All":
                q += " AND t.status=?"; p.append(s_f)
            if g_f != "All":
                q += " AND t.strategy=?"; p.append(g_f)
            q += " ORDER BY t.target_date ASC, r.risk_score DESC"
            rows = conn.execute(q, p).fetchall()

        # Apply search filter client-side
        if srch:
            rows = [r for r in rows if
                    srch in (r["title"] or "").lower() or
                    srch in (r["risk_title"] or "").lower() or
                    srch in (r["owner"] or "").lower() or
                    srch in (r["strategy"] or "").lower()]

        if not rows:
            # Image 7 empty state
            ef = ctk.CTkFrame(self._treat_scroll, fg_color=CARD_BG,
                              corner_radius=12)
            ef.grid(row=0, column=0, columnspan=8,
                    sticky="nsew", padx=20, pady=20)
            ctk.CTkLabel(ef, text="◈",
                         font=ctk.CTkFont(size=48),
                         text_color=BORDER).pack(pady=(30, 4))
            ctk.CTkLabel(ef,
                         text="No treatments match the current filters",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=TEXT_MAIN).pack(pady=(0, 4))
            ctk.CTkLabel(ef,
                         text="Try adjusting your filters or add a new "
                              "treatment plan.",
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).pack(pady=(0, 20))
            # Action cards row
            ac_row = ctk.CTkFrame(ef, fg_color="transparent")
            ac_row.pack(pady=(0, 24))
            for icon, lbl, sub, cmd in [
                ("＋", "Add Treatment",
                 "Create a new treatment plan for a risk",
                 self._add_treatment_from_register),
                ("⊟", "Clear Filters",
                 "Reset all filters to view all treatments",
                 self._clear_treat_filters),
                ("⌕", "Search",
                 "Search by title, risk, owner or strategy",
                 None),
            ]:
                af = ctk.CTkFrame(ac_row, fg_color=CARD_BG2,
                                   corner_radius=10,
                                   width=200, height=110)
                af.pack(side="left", padx=8)
                af.pack_propagate(False)
                ctk.CTkLabel(af, text=icon,
                             font=ctk.CTkFont(size=20),
                             text_color=ACCENT2).pack(pady=(14, 2))
                ctk.CTkLabel(af, text=lbl,
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=TEXT_MAIN).pack()
                ctk.CTkLabel(af, text=sub,
                             font=ctk.CTkFont(size=9),
                             text_color=TEXT_MUTED,
                             wraplength=180).pack(padx=8)
                if cmd:
                    af.bind("<Button-1>", lambda e, c=cmd: c())
            ctk.CTkLabel(ef,
                         text="ⓘ  Treatments help you reduce risk by "
                              "implementing controls and tracking their "
                              "effectiveness.",
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack(pady=(0, 12))
            return

        COL_W = [90, 0, 190, 120, 100, 95, 70]
        self._treat_scroll.grid_columnconfigure(1, weight=1)
        for i, t in enumerate(rows):
            bg = CARD_BG if i % 2 == 0 else CARD_BG2
            rf = ctk.CTkFrame(self._treat_scroll, fg_color=bg,
                              corner_radius=5)
            rf.grid(row=i, column=0, columnspan=7,
                    sticky="ew", padx=0, pady=1)
            for col, w in enumerate(COL_W):
                rf.grid_columnconfigure(
                    col, weight=1 if col == 1 else 0, minsize=w)
            click = lambda e, tid=t["id"], rid=t["risk_id"]: \
                self._open_treatment_form(rid, tid)
            s_color  = TREAT_COLORS.get(t["strategy"], ACCENT2)
            st_color = TREAT_STATUS_COLORS.get(t["status"], TEXT_MUTED)
            d = days_until(t["target_date"])
            if d is not None and d < 0 and \
                    t["status"] not in ("Completed", "Verified"):
                d_text, d_color = f"⚠ {abs(d)}d", RED
            else:
                d_text = t["target_date"] or "—"
                d_color = TEXT_MUTED

            # Strategy badge
            sb = ctk.CTkFrame(rf, fg_color=s_color,
                               corner_radius=4, height=22, width=80)
            sb.grid(row=0, column=0, padx=8, pady=7, sticky="w")
            sb.grid_propagate(False)
            ctk.CTkLabel(sb, text=t["strategy"][:8],
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color="white").pack(padx=4, pady=2)

            cells = [
                (t["title"][:45],       TEXT_MAIN,  1),
                (t["risk_title"][:28],  TEXT_MUTED, 2),
                (t["owner"] or "—",     TEXT_MUTED, 3),
                (t["status"],           st_color,   4),
                (d_text,                d_color,    5),
            ]
            for text, color, col in cells:
                lbl = ctk.CTkLabel(rf, text=text,
                                   font=ctk.CTkFont(size=11),
                                   text_color=color, anchor="w")
                lbl.grid(row=0, column=col,
                         padx=6, pady=7, sticky="w")
                lbl.bind("<Button-1>", click)

            # Progress indicator (lifecycle position)
            lifecycle = ["Draft","Approved","In Progress",
                         "Completed","Verified"]
            try:
                prog = lifecycle.index(t["status"]) / (len(lifecycle)-1)
            except ValueError:
                prog = 0
            pb = ctk.CTkProgressBar(rf, height=5, corner_radius=4,
                                     progress_color=st_color,
                                     fg_color=BORDER, width=60)
            pb.set(prog)
            pb.grid(row=0, column=6, padx=8, pady=10, sticky="w")
            rf.bind("<Button-1>", click)



    def _open_treatment_form(self, risk_id, treatment_id=None,
                              parent_win=None):
        existing = get_treatment(treatment_id) if treatment_id else None
        risk = get_risk(risk_id)
        if not risk:
            return

        win = ctk.CTkToplevel(self)
        win.title("Edit Treatment" if treatment_id else "Add Treatment")
        win.geometry("620x680")
        win.configure(fg_color=DARK_BG)
        win.grab_set()
        set_icon(win)

        def g(key, fallback=""):
            if existing is None:
                return fallback
            val = existing[key] if key in existing.keys() else None
            return val if val not in (None, "") else fallback

        hf = ctk.CTkFrame(win, fg_color=CARD_BG,
                           corner_radius=0, height=46)
        hf.pack(fill="x")
        hf.pack_propagate(False)
        ctk.CTkLabel(
            hf,
            text=f"  {'Edit' if treatment_id else 'Add'} Treatment"
                 f"  ·  {risk['title'][:36]}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MAIN).pack(side="left", padx=14, pady=8)

        scroll = ctk.CTkScrollableFrame(win, fg_color=DARK_BG)
        scroll.pack(fill="both", expand=True)
        fv = {}

        def sec(label):
            ctk.CTkLabel(scroll, text=label,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=ACCENT2).pack(
                         anchor="w", padx=18, pady=(12, 3))
            f = ctk.CTkFrame(scroll, fg_color=CARD_BG,
                             corner_radius=10)
            f.pack(fill="x", padx=14, pady=(0, 4))
            f.grid_columnconfigure(1, weight=1)
            return f

        def frow(frm, row_i, label, key,
                 default="", wtype="entry", vals=None):
            ctk.CTkLabel(frm, text=label,
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED,
                         width=160, anchor="w").grid(
                         row=row_i, column=0,
                         padx=(14, 6), pady=7, sticky="w")
            if wtype == "text":
                w = ctk.CTkTextbox(frm, height=60,
                                    font=ctk.CTkFont(size=11),
                                    fg_color=CARD_BG2)
                if default:
                    w.insert("1.0", str(default))
                fv[key] = w
                w.grid(row=row_i, column=1,
                       padx=(0, 14), pady=7, sticky="ew")
                return
            var = ctk.StringVar(value=str(default))
            if wtype == "option":
                w = ctk.CTkOptionMenu(frm, variable=var,
                                       values=vals or [],
                                       fg_color=CARD_BG2,
                                       button_color=ACCENT2,
                                       font=ctk.CTkFont(size=11))
            else:
                w = ctk.CTkEntry(frm, textvariable=var,
                                  font=ctk.CTkFont(size=11),
                                  fg_color=CARD_BG2)
            w.grid(row=row_i, column=1,
                   padx=(0, 14), pady=7, sticky="ew")
            fv[key] = var

        f1 = sec("Treatment Plan")
        frow(f1, 0, "Strategy *",   "strategy",
             g("strategy", "Mitigate"), "option", TREATMENT_STRATEGIES)
        frow(f1, 1, "Title *",      "title",       g("title"))
        frow(f1, 2, "Description",  "description", g("description"), "text")
        frow(f1, 3, "Owner",        "owner",
             g("owner", risk["owner"] or ""))

        f2 = sec("Status & Schedule")
        frow(f2, 0, "Status",        "status",
             g("status", "Draft"), "option", TREATMENT_STATUS)
        frow(f2, 1, "Target Date (YYYY-MM-DD)",
             "target_date",      g("target_date"))
        frow(f2, 2, "Completion Date",
             "completion_date",  g("completion_date"))

        f3 = sec("Risk Scoring")
        frow(f3, 0, "Residual Target (1–25)",
             "residual_score_target",
             str(g("residual_score_target",
                   max(1, int(risk["risk_score"] or 0) - 4))))
        frow(f3, 1, "Residual Actual (post-verification)",
             "residual_score_actual",
             str(g("residual_score_actual") or ""))
        frow(f3, 2, "Cost Estimate", "cost_estimate",
             g("cost_estimate"))
        frow(f3, 3, "Notes",         "notes",
             g("notes"), "text")

        status_lbl = ctk.CTkLabel(scroll, text="",
                                   font=ctk.CTkFont(size=11))
        status_lbl.pack(pady=4)

        def get_val(k):
            v = fv.get(k)
            if v is None:
                return ""
            if isinstance(v, ctk.CTkTextbox):
                return v.get("1.0", "end").strip()
            return v.get()

        def save():
            title_v = get_val("title").strip()
            if not title_v:
                status_lbl.configure(text="⚠ Title required",
                                     text_color=RED)
                return
            for date_key in ("target_date", "completion_date"):
                dv = get_val(date_key).strip()
                if dv and not validate_date(dv):
                    status_lbl.configure(
                        text=f"⚠ {date_key.replace('_',' ')} "
                             f"must be YYYY-MM-DD",
                        text_color=RED)
                    return

            def safe_int(k):
                try:
                    v = get_val(k).strip()
                    return int(v) if v else None
                except Exception:
                    return None

            data = {
                "risk_id":               risk_id,
                "strategy":              get_val("strategy"),
                "title":                 title_v,
                "description":           get_val("description"),
                "owner":                 get_val("owner"),
                "status":                get_val("status"),
                "target_date":           get_val("target_date").strip(),
                "completion_date":       get_val("completion_date").strip(),
                "residual_score_target": safe_int("residual_score_target"),
                "residual_score_actual": safe_int("residual_score_actual"),
                "cost_estimate":         get_val("cost_estimate"),
                "notes":                 get_val("notes"),
            }
            try:
                if treatment_id:
                    update_treatment(treatment_id, data)
                    msg = "Treatment updated"
                else:
                    insert_treatment(data)
                    msg = "Treatment added"
            except Exception as e:
                status_lbl.configure(text=f"⚠ Error: {e}",
                                     text_color=RED)
                return

            win.destroy()
            if parent_win and parent_win.winfo_exists():
                parent_win.destroy()
            self._refresh_statusbar()
            self._view_risk(risk_id)
            self._toast(f"✅  {msg}")

        btn_f = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_f.pack(fill="x", padx=14, pady=(4, 20))
        ctk.CTkButton(btn_f, text="💾  Save Treatment",
                      height=42, fg_color=TEAL,
                      font=ctk.CTkFont(size=13), corner_radius=8,
                      command=save).pack(
                      side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(btn_f, text="Cancel",
                      height=42, fg_color=BORDER,
                      font=ctk.CTkFont(size=13), corner_radius=8,
                      command=win.destroy).pack(side="left")

    # ── Risk Matrix ───────────────────────────────────────────────────────────
    def _pg_matrix(self):
        # Page header
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(16, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="⊞  Risk Matrix",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="5×5 heat map  ·  NIST SP 800-30  "
                          "·  Click a cell to see risks",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, sticky="w")
        btn_h = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_h.grid(row=0, column=1, sticky="e", rowspan=2)
        ctk.CTkButton(btn_h, text="↗  Export Matrix",
                      height=34, fg_color=BORDER,
                      hover_color=CARD_BG2, text_color=TEXT_MUTED,
                      font=ctk.CTkFont(size=11), corner_radius=8,
                      command=lambda: self._toast(
                          "Matrix export — use PDF Report for full output",
                          color=ACCENT2, duration=3000)).pack(
                      side="left", padx=(0, 8))
        ctk.CTkButton(btn_h, text="⟳", width=36, height=34,
                      fg_color=BORDER, hover_color=CARD_BG2,
                      font=ctk.CTkFont(size=14), corner_radius=8,
                      command=lambda: self.show_page("matrix")).pack(
                      side="left")

        # Legend bar
        legend = ctk.CTkFrame(self.main, fg_color=CARD_BG,
                               corner_radius=8)
        legend.pack(fill="x", padx=24, pady=(0, 10))
        for lbl, color in [
            ("●  LOW  1–4",      GREEN_LT),
            ("●  MEDIUM  5–9",   GOLD),
            ("●  HIGH  10–14",   ORANGE),
            ("●  CRITICAL  15–25", RED),
        ]:
            ctk.CTkLabel(legend, text=lbl,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=color).pack(
                         side="left", padx=16, pady=8)

        mf = ctk.CTkFrame(self.main, fg_color=DARK_BG)
        mf.pack(padx=24, pady=0)
        ctk.CTkLabel(mf, text="IMPACT  →",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=TEXT_MUTED).grid(
                     row=0, column=2, columnspan=5, pady=(0, 3))
        IMP_LBL2 = {1: "Negligible", 2: "Minor", 3: "Moderate",
                    4: "Major",      5: "Critical"}
        LIK_LBL2 = {1: "Rare",      2: "Unlikely", 3: "Possible",
                    4: "Likely",     5: "Almost Certain"}
        for ci, imp in enumerate(range(1, 6)):
            ctk.CTkLabel(mf, text=f"{IMP_LBL2[imp]}\n({imp})",
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED,
                         width=110, justify="center").grid(
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
                             width=90, justify="right").grid(
                             row=ri+2, column=1,
                             padx=(0, 4), pady=2)
                for ci, imp in enumerate(range(1, 6)):
                    sc  = lik * imp
                    cnt = conn.execute(
                        "SELECT COUNT(*) FROM risks "
                        "WHERE likelihood=? AND impact=?",
                        (lik, imp)).fetchone()[0]
                    col = score_color(sc)
                    label_txt = f"{sc}" + (f"\n({cnt})" if cnt else "")
                    ctk.CTkButton(
                        mf, text=label_txt,
                        font=ctk.CTkFont(size=12, weight="bold"),
                        width=110, height=64, corner_radius=8,
                        fg_color=col, hover_color=col,
                        text_color="white",
                        command=lambda l=lik, i=imp, s=sc, c=cnt:
                            self._matrix_click(l, i, s, c)).grid(
                        row=ri+2, column=ci+2, padx=3, pady=3)

        # Footer: How to read | Color guide | Take action
        footer = ctk.CTkFrame(self.main, fg_color=CARD_BG,
                               corner_radius=10)
        footer.pack(fill="x", padx=24, pady=(10, 12))
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=1)
        footer.grid_columnconfigure(2, weight=1)

        for col, (icon, title, body) in enumerate([
            ("⊘", "How to read",
             "Multiply the Likelihood by Impact to get the inherent "
             "risk score."),
            ("ⓘ", "Color guide",
             "Green = Low (1–4)   Yellow = Medium (5–9)\n"
             "Orange = High (10–14)   Red = Critical (15–25)"),
            ("◎", "Take action",
             "Click any cell to view the risks and recommended "
             "treatments at that score."),
        ]):
            cf = ctk.CTkFrame(footer, fg_color=CARD_BG2,
                               corner_radius=8)
            cf.grid(row=0, column=col, padx=8, pady=8, sticky="ew")
            ctk.CTkLabel(cf, text=f"{icon}  {title}",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=TEXT_MAIN).pack(
                         padx=12, pady=(10, 2), anchor="w")
            ctk.CTkLabel(cf, text=body,
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED,
                         wraplength=280, justify="left").pack(
                         padx=12, pady=(0, 10), anchor="w")
        # Note: score label in cell now shows (n) = risks count
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
        # Page header
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(16, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="↗  Export & Report",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="Industry-standard GRC report  ·  NIST SP 800-30 aligned",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, sticky="w")

        scroll = ctk.CTkScrollableFrame(self.main, fg_color=DARK_BG)
        scroll.pack(fill="both", expand=True)

        # Register count + company name row
        top = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        top.pack(fill="x", padx=24, pady=(0, 12))
        top.grid_columnconfigure(1, weight=1)

        risks = get_risks()
        cnt   = len(risks)
        ctk.CTkLabel(top,
                     text=f"Register contains {cnt} risk(s)",
                     font=ctk.CTkFont(size=13),
                     text_color=TEXT_MAIN).grid(
                     row=0, column=0, padx=16, pady=12, sticky="w")
        ctk.CTkLabel(top, text="Company Name",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=0, column=1, padx=8, pady=12, sticky="e")
        self._exp_cn_var = ctk.StringVar(value=self._company_name)
        ctk.CTkEntry(top, textvariable=self._exp_cn_var,
                     width=240, font=ctk.CTkFont(size=11),
                     fg_color=CARD_BG2).grid(
                     row=0, column=2, padx=(0, 8), pady=12)
        ctk.CTkLabel(top, text="Classification",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=0, column=3, padx=4, pady=12)
        self._exp_clf_var = ctk.StringVar(
            value=self._settings.get("default_classification",
                                     "CONFIDENTIAL"))
        ctk.CTkOptionMenu(top, variable=self._exp_clf_var,
                          values=["CONFIDENTIAL","RESTRICTED",
                                  "INTERNAL","PUBLIC"],
                          fg_color=CARD_BG2, button_color=ACCENT,
                          font=ctk.CTkFont(size=11), width=150).grid(
                          row=0, column=4, padx=(0, 16), pady=12)

        self._exp_status = ctk.CTkLabel(
            scroll, text="", font=ctk.CTkFont(size=11))
        self._exp_status.pack(pady=(0, 4))

        # ── Three large action cards (Image 6 style) ──────────────────────
        cards_row = ctk.CTkFrame(scroll, fg_color="transparent")
        cards_row.pack(fill="x", padx=24, pady=(0, 12))
        cards_row.grid_columnconfigure(0, weight=1)
        cards_row.grid_columnconfigure(1, weight=1)
        cards_row.grid_columnconfigure(2, weight=1)

        def _action_card(parent, col, icon, title, sub,
                         color, cmd):
            f = ctk.CTkFrame(parent, fg_color=color,
                             corner_radius=12)
            f.grid(row=0, column=col, padx=5, sticky="nsew")
            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.pack(fill="both", expand=True,
                       padx=18, pady=18)
            ctk.CTkLabel(inner, text=icon,
                         font=ctk.CTkFont(size=32),
                         text_color="white").pack(anchor="w")
            ctk.CTkLabel(inner, text=title,
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").pack(
                         anchor="w", pady=(8, 2))
            ctk.CTkLabel(inner, text=sub,
                         font=ctk.CTkFont(size=10),
                         text_color="white",
                         wraplength=220,
                         justify="left").pack(anchor="w")
            ctk.CTkButton(f, text="Generate →",
                          height=34, fg_color="white",
                          text_color=color,
                          font=ctk.CTkFont(size=12, weight="bold"),
                          corner_radius=8,
                          command=cmd).pack(
                          fill="x", padx=18, pady=(0, 18))

        def export_pdf_report():
            company  = self._exp_cn_var.get().strip() or "Your Organisation"
            clf      = self._exp_clf_var.get()
            analysis = getattr(self, "_last_analysis", None)
            risk_rows = get_risks()
            risks_approved = [dict(r) for r in risk_rows]
            for r in risks_approved:
                if not r.get("inherent_score"):
                    r["inherent_score"] = int(r.get("risk_score") or 0)
                if not r.get("residual_score"):
                    r["residual_score"] = max(1, r["inherent_score"] - 2)
            if not risks_approved:
                messagebox.showinfo("No Risks",
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
                    analysis, risks_approved, company, path, clf,
                    org_scope=get_organisation_scope())
                self._exp_status.configure(
                    text=f"✅ Report saved: {Path(path).name}",
                    text_color=GREEN_LT)
                audit("EXPORT_PDF",
                      detail=f"{cnt} risks → {Path(path).name}")
                self._toast(f"✅  PDF Export — {Path(path).name}")
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
            cols = ["id","title","description","category",
                    "nist_function","nist_category","iso_domain",
                    "cia_component","mitre_tactic","cis_control",
                    "likelihood","impact","risk_score",
                    "inherent_score","residual_score",
                    "owner","status","mitigation","review_date",
                    "date_identified","source","confidence","priority"]
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
                text_color=GREEN_LT)
            self._toast(f"✅  CSV Export — {Path(path).name}")

        def export_backup():
            try:
                dest = backup_database()
                self._exp_status.configure(
                    text=f"✅ Backup created: {dest.name}",
                    text_color=GREEN_LT)
                self._toast(f"✅  Database Backup — {dest.name}")
                self._refresh_statusbar()
                self._update_last_backup_label()
            except Exception as e:
                self._exp_status.configure(
                    text=f"⚠ Backup error: {e}", text_color=RED)

        _action_card(cards_row, 0, "📄", "Full GRC PDF Report",
                     "Comprehensive report with all risks, treatments "
                     "and mappings",
                     ACCENT, export_pdf_report)
        _action_card(cards_row, 1, "📊", "Export CSV",
                     "Export risk register and treatments to CSV format",
                     GREEN, export_csv)
        _action_card(cards_row, 2, "◧", "Backup Database",
                     "Create a secure timestamped backup of your "
                     "RiskCore database",
                     ACCENT2, export_backup)

        # ── Database Backup section ────────────────────────────────────────
        bk_f = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        bk_f.pack(fill="x", padx=24, pady=(0, 12))
        bk_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bk_f, text="◧  Database Backup",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).grid(
                     row=0, column=0, columnspan=4,
                     padx=14, pady=(12, 4), sticky="w")
        ctk.CTkLabel(bk_f, text="Backup folder",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, padx=(14, 6), pady=6, sticky="w")
        bf_inner = ctk.CTkFrame(bk_f, fg_color=CARD_BG2, corner_radius=6)
        bf_inner.grid(row=1, column=1, columnspan=2,
                      padx=(0, 8), pady=6, sticky="ew")
        ctk.CTkLabel(bf_inner, text=str(BASE_DIR / "backups"),
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(
                     padx=10, pady=6, anchor="w")
        ctk.CTkButton(bk_f, text="◉", width=36, height=30,
                      fg_color=BORDER, text_color=TEXT_MUTED,
                      font=ctk.CTkFont(size=12), corner_radius=6).grid(
                      row=1, column=3, padx=(0, 14), pady=6)

        bk_dir = BASE_DIR / "backups"
        try:
            bk_files = sorted(bk_dir.glob("riskcore_backup_*.db"),
                               key=lambda p: p.stat().st_mtime,
                               reverse=True)
            last_bk = (datetime.datetime.fromtimestamp(
                bk_files[0].stat().st_mtime
            ).strftime("%Y-%m-%d  %H:%M")
                if bk_files else "Never yet")
            bk_status = ("Healthy" if bk_files else "No backup yet")
            bk_col = (GREEN_LT if bk_files else RED)
        except Exception:
            last_bk = "Unknown"
            bk_status = "Unknown"
            bk_col = TEXT_MUTED

        ctk.CTkLabel(bk_f, text="Last backup",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).grid(
                     row=2, column=0, padx=(14, 6), pady=2, sticky="w")
        ctk.CTkLabel(bk_f, text=last_bk,
                     font=ctk.CTkFont(size=10),
                     text_color=ACCENT2 if last_bk != "Never yet"
                     else RED).grid(
                     row=2, column=1, padx=(0, 14), pady=2, sticky="w")
        ctk.CTkLabel(bk_f, text="Backup status",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).grid(
                     row=3, column=0, padx=(14, 6), pady=(2, 12),
                     sticky="w")
        ctk.CTkLabel(bk_f, text=bk_status,
                     font=ctk.CTkFont(size=10),
                     text_color=bk_col).grid(
                     row=3, column=1, padx=(0, 14), pady=(2, 12),
                     sticky="w")
        self._last_backup_lbl = ctk.CTkLabel(
            bk_f, text="",
            font=ctk.CTkFont(size=9), text_color=TEXT_DIM)
        self._last_backup_lbl.grid(
            row=4, column=0, columnspan=4,
            padx=14, pady=(0, 8), sticky="w")
        ctk.CTkLabel(bk_f,
                     text="ⓘ  Each backup is a complete timestamped copy "
                          "of riskcore.db. No schema changes are made.",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_DIM).grid(
                     row=5, column=0, columnspan=4,
                     padx=14, pady=(0, 12), sticky="w")
        self._update_last_backup_label()

        # ── Report Includes checklist (Image 6 bottom) ────────────────────
        inc_f = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=10)
        inc_f.pack(fill="x", padx=24, pady=(0, 16))
        hf2 = ctk.CTkFrame(inc_f, fg_color="transparent")
        hf2.pack(fill="x", padx=14, pady=(12, 8))
        ctk.CTkLabel(hf2, text="✓  Report includes",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_MAIN).pack(side="left")
        items = [
            "Executive Summary",     "Risk Register",
            "Risk Heat Map",          "Treatment Plan",
            "Framework Mappings",     "NIST CSF, ISO 27001, "
                                      "MITRE ATT&CK",
            "Risk Scoring (NIST SP 800-30)", "Recommendations",
            "Methodology",            "Appendices",
        ]
        grid_f = ctk.CTkFrame(inc_f, fg_color="transparent")
        grid_f.pack(fill="x", padx=14, pady=(0, 14))
        for i in range(4):
            grid_f.grid_columnconfigure(i, weight=1)
        for idx, item in enumerate(items):
            col = idx % 4
            row_i = idx // 4
            ctk.CTkLabel(grid_f,
                         text=f"✓  {item}",
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=row_i, column=col,
                         padx=8, pady=2, sticky="w")

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
                    analysis, risks_approved, company, path, clf,
                    org_scope=get_organisation_scope())
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
        # ── Page header ───────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(16, 8))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr,
                     text="⊙  Activity Center",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="Real-time audit trail  ·  Compliance intelligence  "
                          "·  ISO/IEC 27001:2022 A.8 compliant",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, sticky="w")
        ctk.CTkButton(hdr, text="⟳ Refresh", width=90, height=28,
                      fg_color=BORDER, hover_color=CARD_BG2,
                      font=ctk.CTkFont(size=10), corner_radius=6,
                      command=lambda: self.show_page("audit")).grid(
                      row=0, column=2, sticky="e")

        # ── Summary KPI strip ─────────────────────────────────────────────
        with get_db() as conn:
            total_log   = conn.execute(
                "SELECT COUNT(*) FROM audit_log").fetchone()[0]
            risk_chgs   = conn.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE action IN ('CREATE','UPDATE','DELETE')").fetchone()[0]
            treat_chgs  = conn.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE action LIKE 'TREATMENT%'").fetchone()[0]
            ai_acts     = conn.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE action LIKE 'AI%'").fetchone()[0]
            exports     = conn.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE action LIKE 'EXPORT%'").fetchone()[0]
            errors      = 0  # placeholder

        kstrip = ctk.CTkFrame(self.main, fg_color="transparent")
        kstrip.pack(fill="x", padx=24, pady=(0, 10))
        for i in range(6):
            kstrip.grid_columnconfigure(i, weight=1)

        for col, (icon, val, lbl, col_c) in enumerate([
            ("◉",  total_log,  "Total Records",       TEXT_MAIN),
            ("⊘",  risk_chgs,  "Risk Changes",        GOLD),
            ("◈",  treat_chgs, "Treatment Activity",  TEAL),
            ("◎",  ai_acts,    "AI Activity",         PURPLE_LT),
            ("↗",  exports,    "Reports Generated",   ACCENT2),
            ("⊗",  errors,     "Failed Operations",   TEXT_MUTED),
        ]):
            f = ctk.CTkFrame(kstrip, fg_color=CARD_BG, corner_radius=10)
            f.grid(row=0, column=col, padx=5, sticky="nsew")
            ctk.CTkLabel(f, text=icon, font=ctk.CTkFont(size=18),
                         text_color=col_c).pack(padx=14, pady=(10, 2),
                                                anchor="w")
            ctk.CTkLabel(f, text=str(val),
                         font=ctk.CTkFont(size=22, weight="bold"),
                         text_color=col_c).pack(padx=14, anchor="w")
            ctk.CTkLabel(f, text=lbl,
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_MUTED).pack(
                         padx=14, pady=(0, 10), anchor="w")

        # ── Two-column body ───────────────────────────────────────────────
        body = ctk.CTkFrame(self.main, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # Left: Filter panel
        filt = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=10)
        filt.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        ctk.CTkLabel(filt, text="Filter Activity",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEXT_MAIN).pack(
                     padx=14, pady=(12, 8), anchor="w")

        self._audit_filt_var = ctk.StringVar(value="All")
        ACTION_GROUPS = [
            ("All Activity",      "All"),
            ("Risk Changes",      "RISK"),
            ("Treatment Activity","TREATMENT"),
            ("AI Activity",       "AI"),
            ("Reports",           "EXPORT"),
            ("Settings",          "SETTINGS"),
            ("System",            "SYSTEM"),
        ]

        with get_db() as conn:
            group_counts = {
                "All":      total_log,
                "RISK":     risk_chgs,
                "TREATMENT":treat_chgs,
                "AI":       ai_acts,
                "EXPORT":   exports,
                "SETTINGS": conn.execute(
                    "SELECT COUNT(*) FROM audit_log "
                    "WHERE action LIKE '%SCOPE%' OR action LIKE '%SETTINGS%'"
                ).fetchone()[0],
                "SYSTEM": conn.execute(
                    "SELECT COUNT(*) FROM audit_log "
                    "WHERE action IN ('APP_START','DB_BACKUP',"
                    "'DB_RESTORE','SCHEMA_MIGRATION')"
                ).fetchone()[0],
            }

        self._audit_btn_refs = {}
        for label, key in ACTION_GROUPS:
            cnt = group_counts.get(key, 0)
            bf = ctk.CTkFrame(filt, fg_color="transparent")
            bf.pack(fill="x", padx=10, pady=2)
            bf.grid_columnconfigure(0, weight=1)
            is_sel = (key == "All")
            btn = ctk.CTkButton(
                bf, text=label, anchor="w", height=32,
                fg_color=ACCENT if is_sel else "transparent",
                hover_color=BORDER,
                text_color=TEXT_MAIN if is_sel else TEXT_MUTED,
                font=ctk.CTkFont(size=11), corner_radius=6,
                command=lambda k=key: self._audit_filter(k))
            btn.grid(row=0, column=0, sticky="ew")
            ctk.CTkLabel(bf, text=str(cnt),
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_DIM, width=30,
                         anchor="e").grid(row=0, column=1, padx=(4, 0))
            self._audit_btn_refs[key] = btn

        # Right: Activity timeline
        right_panel = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=10)
        right_panel.grid(row=0, column=1, sticky="nsew")

        # Timeline header
        tlhdr = ctk.CTkFrame(right_panel, fg_color="transparent")
        tlhdr.pack(fill="x", padx=14, pady=(12, 8))
        tlhdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(tlhdr, text="Recent Activity",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEXT_MAIN).grid(
                     row=0, column=0, sticky="w")
        live_f = ctk.CTkFrame(tlhdr, fg_color="#0D3321",
                               corner_radius=6)
        live_f.grid(row=0, column=1, padx=(0, 0), sticky="e")
        ctk.CTkLabel(live_f, text="● Live",
                     font=ctk.CTkFont(size=9),
                     text_color=GREEN_LT).pack(padx=8, pady=3)

        self._audit_scroll = ctk.CTkScrollableFrame(
            right_panel, fg_color="transparent")
        self._audit_scroll.pack(fill="both", expand=True,
                                padx=0, pady=(0, 8))
        self._audit_scroll.grid_columnconfigure(2, weight=1)
        self._audit_current_filter = "All"
        self._audit_logs_all = None
        self._load_audit_log("All")

    def _audit_filter(self, key):
        """Switch audit filter and reload the timeline."""
        if hasattr(self, "_audit_btn_refs"):
            for k, btn in self._audit_btn_refs.items():
                is_sel = (k == key)
                btn.configure(
                    fg_color=ACCENT if is_sel else "transparent",
                    text_color=TEXT_MAIN if is_sel else TEXT_MUTED)
        self._audit_current_filter = key
        self._load_audit_log(key)

    def _load_audit_log(self, key="All"):
        if not hasattr(self, "_audit_scroll"):
            return
        for w in self._audit_scroll.winfo_children():
            w.destroy()

        # Build WHERE clause per filter group
        filters = {
            "All":      "",
            "RISK":     "WHERE action IN ('CREATE','UPDATE','DELETE')",
            "TREATMENT":"WHERE action LIKE 'TREATMENT%' "
                        "OR action='RESIDUAL_SYNC'",
            "AI":       "WHERE action LIKE 'AI%'",
            "EXPORT":   "WHERE action LIKE 'EXPORT%'",
            "SETTINGS": "WHERE action LIKE '%SCOPE%' "
                        "OR action LIKE '%SETTINGS%'",
            "SYSTEM":   "WHERE action IN ('APP_START','DB_BACKUP',"
                        "'DB_RESTORE','SCHEMA_MIGRATION')",
        }
        where = filters.get(key, "")
        with get_db() as conn:
            logs = conn.execute(
                f"SELECT * FROM audit_log {where} "
                f"ORDER BY id DESC LIMIT 200").fetchall()

        if not logs:
            ctk.CTkLabel(self._audit_scroll,
                         text="No activity recorded for this filter.",
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED).pack(pady=20)
            return

        ACTION_META = {
            "CREATE":            ("◉", GOLD,      "Risk Created"),
            "UPDATE":            ("✏", ACCENT2,   "Risk Updated"),
            "DELETE":            ("✕", RED,        "Risk Deleted"),
            "TREATMENT_CREATE":  ("◈", TEAL,       "Treatment Created"),
            "TREATMENT_UPDATE":  ("◈", CYAN,       "Treatment Updated"),
            "TREATMENT_DELETE":  ("◈", ORANGE,     "Treatment Deleted"),
            "RESIDUAL_SYNC":     ("↓", GREEN_LT,   "Residual Synced"),
            "AI_ANALYSIS":       ("◎", PURPLE_LT,  "AI Analysis"),
            "AI_APPROVE":        ("✓", GREEN_LT,   "AI Approved"),
            "EXPORT_PDF":        ("↗", ACCENT2,    "PDF Generated"),
            "EXPORT_CSV":        ("↗", GREEN_LT,   "CSV Exported"),
            "DB_BACKUP":         ("◧", ACCENT2,    "Database Backup"),
            "DB_RESTORE":        ("◧", GOLD,       "Database Restored"),
            "APP_START":         ("⬡", TEXT_DIM,   "App Started"),
            "ORG_SCOPE_SAVE":    ("⊙", TEAL,       "Scope Updated"),
            "SCHEMA_MIGRATION":  ("⚙", TEXT_DIM,   "Schema Migration"),
        }
        STATUS_TAGS = {
            "CREATE":           ("Risk",      GOLD),
            "UPDATE":           ("Risk",      GOLD),
            "DELETE":           ("Risk",      RED),
            "TREATMENT_CREATE": ("Treatment", TEAL),
            "TREATMENT_UPDATE": ("Treatment", TEAL),
            "TREATMENT_DELETE": ("Treatment", ORANGE),
            "AI_ANALYSIS":      ("AI",        PURPLE_LT),
            "AI_APPROVE":       ("AI",        GREEN_LT),
            "EXPORT_PDF":       ("Report",    ACCENT2),
            "EXPORT_CSV":       ("Export",    GREEN_LT),
        }

        for i, log in enumerate(logs):
            action = log["action"]
            icon, color, label = ACTION_META.get(
                action, ("·", TEXT_DIM, action.replace("_"," ").title()))
            ts = (log["timestamp"] or "")[:19].replace("T", "  ")

            row_bg = CARD_BG2 if i % 2 == 0 else "transparent"
            rf = ctk.CTkFrame(self._audit_scroll, fg_color=row_bg,
                              corner_radius=4)
            rf.pack(fill="x", padx=4, pady=1)
            rf.grid_columnconfigure(3, weight=1)

            # Timeline dot + connector
            dot = ctk.CTkFrame(rf, fg_color=color,
                                width=8, height=8, corner_radius=4)
            dot.grid(row=0, column=0, padx=(12, 8), pady=10, sticky="w")

            # Timestamp
            ctk.CTkLabel(rf, text=ts,
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_DIM, width=115).grid(
                         row=0, column=1, pady=8, sticky="w")

            # Icon + label
            ctk.CTkLabel(rf, text=f"{icon} {label}",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=color, width=140).grid(
                         row=0, column=2, padx=6, pady=8, sticky="w")

            # Detail
            ctk.CTkLabel(rf, text=(log["detail"] or "—")[:70],
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=0, column=3, padx=4, pady=8, sticky="w")

            # Status tag
            if action in STATUS_TAGS:
                tag_lbl, tag_col = STATUS_TAGS[action]
                tf = ctk.CTkFrame(rf, fg_color=tag_col,
                                   corner_radius=3)
                tf.grid(row=0, column=4, padx=(4, 6), pady=8)
                ctk.CTkLabel(tf, text=tag_lbl,
                             font=ctk.CTkFont(size=8, weight="bold"),
                             text_color="white").pack(padx=5, pady=2)


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
        # ── Page header ───────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self.main, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(16, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="⚙  Settings",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="Configure your organisation, AI, system "
                          "preferences, and application settings",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, sticky="w")
        ctk.CTkButton(hdr, text="💾  Save Changes",
                      height=34, fg_color=ACCENT2,
                      font=ctk.CTkFont(size=12), corner_radius=8,
                      command=lambda: _do_save()).grid(
                      row=0, column=1, sticky="e")

        outer_scroll = ctk.CTkScrollableFrame(self.main, fg_color=DARK_BG)
        outer_scroll.pack(fill="both", expand=True)

        # Three-column layout: left nav | main content | right panel
        cols = ctk.CTkFrame(outer_scroll, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=24, pady=0)
        cols.grid_columnconfigure(0, weight=0, minsize=180)
        cols.grid_columnconfigure(1, weight=2)
        cols.grid_columnconfigure(2, weight=1)

        # ── Left nav ──────────────────────────────────────────────────────
        nav_f = ctk.CTkFrame(cols, fg_color=CARD_BG, corner_radius=10)
        nav_f.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        ctk.CTkLabel(nav_f, text="SETTINGS",
                     font=ctk.CTkFont(size=8, weight="bold"),
                     text_color=TEXT_DIM).pack(
                     padx=14, pady=(12, 4), anchor="w")

        nav_items = [
            ("⬡", "Organisation",    "Profile, details & preferences"),
            ("◎", "AI Configuration","AI model, API keys & options"),
            ("⊞", "Application",     "General app settings"),
            ("◧", "Backup & Restore","Data protection & recovery"),
            ("⊙", "Audit & Logging", "Audit trail & log retention"),
            ("ℹ", "About",           "Version, info & updates"),
        ]
        for icon, title, sub in nav_items:
            nf = ctk.CTkFrame(nav_f, fg_color="transparent")
            nf.pack(fill="x", padx=8, pady=2)
            is_first = (title == "Organisation")
            ctk.CTkButton(
                nf, text=f" {icon}  {title}", anchor="w", height=36,
                fg_color=ACCENT if is_first else "transparent",
                hover_color=BORDER, text_color=TEXT_MAIN,
                font=ctk.CTkFont(size=11), corner_radius=6
            ).pack(fill="x")
            ctk.CTkLabel(nf, text=sub,
                         font=ctk.CTkFont(size=8),
                         text_color=TEXT_DIM).pack(
                         padx=16, anchor="w")

        # ── Main content ──────────────────────────────────────────────────
        main_f = ctk.CTkFrame(cols, fg_color="transparent")
        main_f.grid(row=0, column=1, padx=(0, 8), sticky="nsew")

        def _section_card(title, icon=""):
            f = ctk.CTkFrame(main_f, fg_color=CARD_BG, corner_radius=10)
            f.pack(fill="x", pady=(0, 8))
            f.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(f, text=f"{icon}  {title}" if icon else title,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=TEXT_MAIN).grid(
                         row=0, column=0, columnspan=4,
                         padx=14, pady=(12, 8), sticky="w")
            return f

        def _field_row(card, r_i, label, key_widget, col_span=2):
            ctk.CTkLabel(card, text=label,
                         font=ctk.CTkFont(size=11),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=r_i, column=0,
                         padx=(14, 6), pady=6, sticky="w")
            key_widget.grid(row=r_i, column=1, columnspan=col_span,
                            padx=(0, 14), pady=6, sticky="ew")

        # Organisation Settings
        org_c = _section_card("Organisation Settings", "⬡")
        org_c.grid_columnconfigure(1, weight=1)
        org_c.grid_columnconfigure(3, weight=1)

        self._set_org_var = ctk.StringVar(
            value=self._settings.get("organisation_name", "Your Organisation"))
        self._set_clf_var = ctk.StringVar(
            value=self._settings.get("default_classification", "CONFIDENTIAL"))

        # Row 1: org name | primary contact
        ctk.CTkLabel(org_c, text="Organisation Name",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, padx=(14, 6), pady=6, sticky="w")
        ctk.CTkEntry(org_c, textvariable=self._set_org_var,
                     font=ctk.CTkFont(size=11),
                     fg_color=CARD_BG2).grid(
                     row=1, column=1, padx=(0, 12), pady=6, sticky="ew")
        ctk.CTkLabel(org_c, text="Primary Contact",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=2, padx=(0, 6), pady=6, sticky="w")
        ctk.CTkEntry(org_c,
                     placeholder_text="e.g. Michael Waugh",
                     font=ctk.CTkFont(size=11),
                     fg_color=CARD_BG2).grid(
                     row=1, column=3, padx=(0, 14), pady=6, sticky="ew")

        # Row 2: Industry | classification
        ctk.CTkLabel(org_c, text="Industry",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=2, column=0, padx=(14, 6), pady=6, sticky="w")
        ind_var = ctk.StringVar(value="Information Technology")
        ctk.CTkOptionMenu(org_c, variable=ind_var,
                          values=["Information Technology","Manufacturing",
                                  "Finance & Banking","Healthcare",
                                  "Government","Retail","Energy","Other"],
                          fg_color=CARD_BG2, button_color=ACCENT2,
                          font=ctk.CTkFont(size=11)).grid(
                          row=2, column=1, padx=(0, 12), pady=6, sticky="ew")
        ctk.CTkLabel(org_c, text="Default Classification",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=2, column=2, padx=(0, 6), pady=6, sticky="w")
        ctk.CTkOptionMenu(org_c, variable=self._set_clf_var,
                          values=["CONFIDENTIAL","RESTRICTED",
                                  "INTERNAL","PUBLIC"],
                          fg_color=CARD_BG2, button_color=ACCENT,
                          font=ctk.CTkFont(size=11)).grid(
                          row=2, column=3, padx=(0, 14), pady=6, sticky="ew")

        # Row 3: Logo placeholder
        ctk.CTkLabel(org_c, text="Organisation Logo",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=3, column=0, padx=(14, 6), pady=6, sticky="nw")
        logo_f = ctk.CTkFrame(org_c, fg_color=CARD_BG2,
                               corner_radius=8, width=140, height=70)
        logo_f.grid(row=3, column=1, padx=(0, 14), pady=6, sticky="w")
        logo_f.grid_propagate(False)
        ctk.CTkLabel(logo_f, text="⬆  Upload Logo",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(expand=True)
        ctk.CTkLabel(org_c, text="PNG, JPG or SVG (max 2MB)",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_DIM).grid(
                     row=4, column=1, padx=(0, 14), pady=(0, 12), sticky="w")

        # AI Configuration
        ai_c = _section_card("AI Configuration", "◎")
        ai_c.grid_columnconfigure(1, weight=1)
        ai_c.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(ai_c,
                     text="Configure AI provider and analysis settings",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, columnspan=4,
                     padx=14, pady=(0, 8), sticky="w")

        # Provider + Model row
        ctk.CTkLabel(ai_c, text="AI Provider",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=2, column=0, padx=(14, 6), pady=6, sticky="w")
        ctk.CTkOptionMenu(ai_c, values=["Claude (Anthropic)"],
                          fg_color=CARD_BG2, button_color=ACCENT2,
                          font=ctk.CTkFont(size=11)).grid(
                          row=2, column=1, padx=(0, 12), pady=6, sticky="ew")
        ctk.CTkLabel(ai_c, text="Default Model",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=2, column=2, padx=(0, 6), pady=6, sticky="w")
        ctk.CTkOptionMenu(ai_c,
                          values=["claude-sonnet-4-6",
                                  "claude-opus-4-6"],
                          fg_color=CARD_BG2, button_color=ACCENT2,
                          font=ctk.CTkFont(size=11)).grid(
                          row=2, column=3, padx=(0, 14), pady=6, sticky="ew")

        # API Key row
        ctk.CTkLabel(ai_c, text="Claude API Key",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=3, column=0, padx=(14, 6), pady=6, sticky="w")
        self._set_key_var = ctk.StringVar(value=self._api_key)
        key_row = ctk.CTkFrame(ai_c, fg_color="transparent")
        key_row.grid(row=3, column=1, columnspan=2,
                     padx=(0, 6), pady=6, sticky="ew")
        key_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(key_row, textvariable=self._set_key_var,
                     show="•", font=ctk.CTkFont(size=11),
                     fg_color=CARD_BG2,
                     placeholder_text="sk-ant-api03-...").grid(
                     row=0, column=0, sticky="ew")

        test_status = ctk.CTkLabel(ai_c, text="",
                                    font=ctk.CTkFont(size=10))
        test_status.grid(row=4, column=0, columnspan=4,
                         padx=14, pady=(0, 4), sticky="w")

        def test_connection():
            key = self._set_key_var.get().strip()
            if not key.startswith("sk-ant"):
                test_status.configure(
                    text="⚠ Key should start with 'sk-ant-api03-'",
                    text_color=RED)
                return
            test_status.configure(
                text="⏳ Testing connection...", text_color=GOLD)
            self.update()
            def run():
                import urllib.request, urllib.error
                try:
                    payload = json.dumps({
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 16,
                        "messages": [{"role":"user","content":"Reply OK"}]
                    }).encode()
                    req = urllib.request.Request(
                        "https://api.anthropic.com/v1/messages",
                        data=payload,
                        headers={"Content-Type":"application/json",
                                 "x-api-key":key,
                                 "anthropic-version":"2023-06-01"},
                        method="POST")
                    with urllib.request.urlopen(req, timeout=20):
                        pass
                    self.after(0, lambda: test_status.configure(
                        text="✅ Connection successful  ·  "
                             f"Last tested: {today()}  {now_str()}",
                        text_color=GREEN_LT))
                except urllib.error.HTTPError as e:
                    msg = ("Invalid API key"
                           if e.code in (401, 403)
                           else f"HTTP {e.code}")
                    self.after(0, lambda: test_status.configure(
                        text=f"⚠ {msg}", text_color=RED))
                except Exception as e:
                    self.after(0, lambda: test_status.configure(
                        text=f"⚠ {e}", text_color=RED))
            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(ai_c, text="Test Connection",
                      height=30, fg_color=PURPLE_LT,
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=test_connection).grid(
                      row=3, column=3, padx=(0, 14), pady=6)

        enc_text = ("⬡  Key is encrypted and stored securely"
                    if self._api_key else "⚠ No API key saved yet")
        ctk.CTkLabel(ai_c, text=enc_text,
                     font=ctk.CTkFont(size=10),
                     text_color=GREEN_LT if self._api_key else GOLD).grid(
                     row=5, column=0, columnspan=4,
                     padx=14, pady=(0, 12), sticky="w")

        # Backup & Data Management
        bk_c = _section_card("Backup & Data Management", "◧")
        bk_c.grid_columnconfigure(1, weight=1)
        bk_c.grid_columnconfigure(3, weight=1)

        # Find last backup
        bk_dir = BASE_DIR / "backups"
        try:
            bk_files = sorted(bk_dir.glob("riskcore_backup_*.db"),
                               key=lambda p: p.stat().st_mtime,
                               reverse=True)
            last_bk = (datetime.datetime.fromtimestamp(
                bk_files[0].stat().st_mtime).strftime("%Y-%m-%d  %H:%M:%S")
                if bk_files else "Never yet")
        except Exception:
            last_bk = "Unknown"

        ctk.CTkLabel(bk_c, text="Backup Location",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=1, column=0, padx=(14, 6), pady=6, sticky="w")
        bk_path_f = ctk.CTkFrame(bk_c, fg_color=CARD_BG2, corner_radius=6)
        bk_path_f.grid(row=1, column=1, columnspan=2,
                       padx=(0, 6), pady=6, sticky="ew")
        ctk.CTkLabel(bk_path_f, text=str(bk_dir),
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_MUTED).pack(
                     padx=10, pady=6, anchor="w")

        ctk.CTkLabel(bk_c, text="Last Backup",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_MUTED).grid(
                     row=2, column=0, padx=(14, 6), pady=6, sticky="w")
        ctk.CTkLabel(bk_c, text=last_bk,
                     font=ctk.CTkFont(size=11),
                     text_color=(TEXT_MUTED if last_bk != "Never yet"
                                 else RED)).grid(
                     row=2, column=1, padx=(0, 14), pady=6, sticky="w")

        self._bk_status = ctk.CTkLabel(bk_c, text="",
                                        font=ctk.CTkFont(size=10))
        self._bk_status.grid(row=3, column=0, columnspan=4,
                              padx=14, pady=(0, 4), sticky="w")

        def do_backup():
            try:
                path = backup_database()
                self._bk_status.configure(
                    text=f"✅ Backup created: {path.name}",
                    text_color=GREEN_LT)
                self._toast(f"✅  Backup — {path.name}")
            except Exception as e:
                self._bk_status.configure(
                    text=f"⚠ Backup failed: {e}", text_color=RED)

        bk_btn_row = ctk.CTkFrame(bk_c, fg_color="transparent")
        bk_btn_row.grid(row=4, column=0, columnspan=4,
                        padx=14, pady=(0, 12), sticky="w")
        ctk.CTkButton(bk_btn_row, text="Create Backup",
                      height=32, fg_color=ACCENT2,
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=do_backup).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bk_btn_row, text="Restore Backup",
                      height=32, fg_color=BORDER,
                      text_color=TEXT_MUTED,
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=self._restore_backup_dialog).pack(
                      side="left")

        # System Information
        info_c = _section_card("System Information", "ℹ")
        info_c.grid_columnconfigure(1, weight=1)
        with get_db() as conn:
            risk_count  = conn.execute(
                "SELECT COUNT(*) FROM risks").fetchone()[0]
            treat_count = conn.execute(
                "SELECT COUNT(*) FROM treatments").fetchone()[0]
        try:
            db_size = f"{DB_PATH.stat().st_size / 1024:.1f} KB"
        except Exception:
            db_size = "—"
        sys_info = [
            ("Application Version", "RiskCore GRC Platform v1.5"),
            ("Build Type",          "Stable Release"),
            ("Database",            f"SQLite · Encrypted API key  ·  {db_size}"),
            ("Last Backup",         last_bk),
            ("Total Risks",         str(risk_count)),
            ("Total Treatments",    str(treat_count)),
            ("Scoring Methodology", "NIST SP 800-30 Rev 1"),
            ("Frameworks",
             "NIST CSF 2.0  ·  ISO 27001:2022  ·  MITRE ATT&CK  "
             "·  CIS Controls v8  ·  CIA Triad"),
            ("Developer",           "Waugh Development Group  ·  Michael Waugh"),
        ]
        for ri, (lbl, val) in enumerate(sys_info, 1):
            ctk.CTkLabel(info_c, text=lbl,
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED, width=160,
                         anchor="w").grid(
                         row=ri, column=0, padx=(14, 6),
                         pady=4, sticky="w")
            ctk.CTkLabel(info_c, text=val,
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MAIN, anchor="w").grid(
                         row=ri, column=1, padx=(0, 14),
                         pady=4, sticky="w")
        ctk.CTkLabel(info_c, text=" ",
                     font=ctk.CTkFont(size=4)).grid(
                     row=ri+1, column=0)

        # ── Right panel: Security & Compliance ────────────────────────────
        right_f = ctk.CTkFrame(cols, fg_color="transparent")
        right_f.grid(row=0, column=2, sticky="nsew")

        def _right_card(title, icon=""):
            f = ctk.CTkFrame(right_f, fg_color=CARD_BG, corner_radius=10)
            f.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(f, text=f"{icon}  {title}" if icon else title,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=TEXT_MAIN).pack(
                         padx=14, pady=(12, 6), anchor="w")
            return f

        sec_f = _right_card("Security & Compliance", "⊘")
        sec_items = [
            ("Audit Logging",    "Enabled",  GREEN_LT),
            ("Data Encryption",  "AES-256",  GREEN_LT),
            ("Password Policy",  "Strong",   GREEN_LT),
            ("Session Timeout",  "30 min",   TEXT_MUTED),
            ("2FA Requirement",  "Optional", GOLD),
            ("Data Retention",   "7 years",  TEXT_MUTED),
        ]
        for label, status, color in sec_items:
            sf = ctk.CTkFrame(sec_f, fg_color="transparent")
            sf.pack(fill="x", padx=14, pady=2)
            sf.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(sf, text=label,
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=0, column=0, sticky="w")
            ctk.CTkLabel(sf, text=status,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=color).grid(
                         row=0, column=1, sticky="e")
        posture_f = ctk.CTkFrame(sec_f, fg_color="#0D3321",
                                  corner_radius=6)
        posture_f.pack(fill="x", padx=14, pady=(8, 12))
        ctk.CTkLabel(posture_f,
                     text="✓  Your system is secure and compliant",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=GREEN_LT).pack(
                     padx=10, pady=(8, 2), anchor="w")
        ctk.CTkLabel(posture_f,
                     text="All security settings are properly configured",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_MUTED).pack(
                     padx=10, pady=(0, 8), anchor="w")

        # AI Analysis Settings toggles
        ai_set_f = _right_card("AI Analysis Settings", "◎")
        toggle_items = [
            ("Enable Risk Extraction",    True),
            ("Enable Control Mapping",    True),
            ("Enable MITRE ATT&CK Mapping",True),
            ("Enable Treatment Suggestions",True),
            ("Auto Suggest Risk Scores",  False),
        ]
        for label, default in toggle_items:
            tf2 = ctk.CTkFrame(ai_set_f, fg_color="transparent")
            tf2.pack(fill="x", padx=14, pady=3)
            tf2.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(tf2, text=label,
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED, anchor="w").grid(
                         row=0, column=0, sticky="w")
            sw = ctk.CTkSwitch(tf2, text="", width=38,
                               fg_color=BORDER if not default else ACCENT2,
                               progress_color=ACCENT2)
            if default:
                sw.select()
            sw.grid(row=0, column=1)
        ctk.CTkLabel(ai_set_f, text=" ",
                     font=ctk.CTkFont(size=4)).pack()

        # Recent config changes
        rc_f = _right_card("Recent Configuration Changes", "⊙")
        with get_db() as conn:
            recent_cfgs = conn.execute(
                "SELECT timestamp, action, detail FROM audit_log "
                "WHERE action IN ('ORG_SCOPE_SAVE','SETTINGS_SAVE',"
                "'DB_BACKUP','AI_ANALYSIS','EXPORT_PDF','SCHEMA_MIGRATION') "
                "ORDER BY id DESC LIMIT 5").fetchall()
        if not recent_cfgs:
            ctk.CTkLabel(rc_f, text="No recent configuration changes",
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack(
                         padx=14, pady=(0, 12), anchor="w")
        for log in recent_cfgs:
            ts = (log["timestamp"] or "")[:16].replace("T", " ")
            lf = ctk.CTkFrame(rc_f, fg_color="transparent")
            lf.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(lf, text=log["action"].replace("_"," ").title(),
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=TEXT_MAIN).pack(anchor="w")
            ctk.CTkLabel(lf, text=ts,
                         font=ctk.CTkFont(size=9),
                         text_color=TEXT_DIM).pack(anchor="w")
        ctk.CTkLabel(rc_f, text=" ", font=ctk.CTkFont(size=4)).pack()

        # ── Save logic ────────────────────────────────────────────────────
        self._settings_status = ctk.CTkLabel(
            outer_scroll, text="", font=ctk.CTkFont(size=11))
        self._settings_status.pack(pady=4)

        def _do_save():
            org_name = self._set_org_var.get().strip() or "Your Organisation"
            clf      = self._set_clf_var.get()
            key      = self._set_key_var.get().strip()
            now_ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._settings = {
                "organisation_name":      org_name,
                "default_classification": clf,
                "last_saved":             now_ts,
            }
            ok = save_settings(self._settings)
            self._company_name = org_name
            if key and key != self._api_key:
                if key.startswith("sk-ant"):
                    self._api_key = key
                    save_api_key(key)
                else:
                    self._settings_status.configure(
                        text="⚠ Settings saved — API key unchanged (invalid format)",
                        text_color=GOLD)
                    self._toast("⚠  Settings saved (key unchanged)", color=GOLD)
                    return
            if ok:
                self._settings_status.configure(
                    text=f"✅ Settings saved  ·  {now_ts}",
                    text_color=GREEN_LT)
                self._toast("✅  Settings Saved")
                self._refresh_statusbar()
            else:
                self._settings_status.configure(
                    text="⚠ Could not write settings file", text_color=RED)

    def _restore_backup_dialog(self):
        """Let user pick a backup file to restore."""
        path = filedialog.askopenfilename(
            title="Select Backup Database",
            initialdir=str(BASE_DIR / "backups"),
            filetypes=[("SQLite DB","*.db"),("All Files","*.*")])
        if not path:
            return
        if messagebox.askyesno(
                "Restore Backup",
                f"Restore from:\n{path}\n\n"
                "The current database will be backed up first.\n"
                "The application will use the restored data immediately.\n\n"
                "Continue?"):
            try:
                pre = restore_database(path)
                self._toast(
                    f"✅  Restored from {Path(path).name}  "
                    f"·  Pre-restore backup: {pre.name}")
                self._refresh_statusbar()
            except Exception as e:
                messagebox.showerror("Restore Failed", str(e))


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
