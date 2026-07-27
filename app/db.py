"""
SQLite data layer for the ESSFTA Foundation Breeders' Showcase.

Design note: the whole point of this app (vs. the JotForm attempt that
"jumbled up") is structural integrity. Every dog carries a `kennel_id`
foreign key, so a kennel *owns* its dogs by relation — never by row order
in a spreadsheet. Repeatable sub-lists that don't need their own identity
(mentors, venues, our_dogs, at_stud, planned_breedings, pedigree) are stored
as JSON blobs on the owning row.
"""
import json
import sqlite3
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_token(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # safe concurrent readers/writer
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS kennels (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    edit_token          TEXT UNIQUE NOT NULL,   -- private return link
    login_email         TEXT NOT NULL,          -- who owns/created this entry
    status              TEXT NOT NULL DEFAULT 'draft',  -- draft | submitted
    show_year           INTEGER NOT NULL,

    kennel_name         TEXT DEFAULT '',
    owner_name          TEXT DEFAULT '',
    location_address    TEXT DEFAULT '',
    email               TEXT DEFAULT '',        -- public contact email
    phone               TEXT DEFAULT '',
    social_media        TEXT DEFAULT '',
    year_started        TEXT DEFAULT '',
    breeding_philosophy TEXT DEFAULT '',

    mentors_json        TEXT DEFAULT '[]',      -- up to 3 strings
    prominent_json      TEXT DEFAULT '[]',      -- up to 4 strings
    health_json         TEXT DEFAULT '{}',      -- {Hips: true, ...}
    venues_json         TEXT DEFAULT '[]',      -- selected venue strings
    our_dogs_json       TEXT DEFAULT '[]',      -- [{name, highlights}] up to 4
    at_stud_json        TEXT DEFAULT '[]',      -- [{name, dob, certs}] up to 2
    planned_json        TEXT DEFAULT '[]',      -- [{sire_dam, whelp}] up to 2

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dogs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    kennel_id           INTEGER NOT NULL REFERENCES kennels(id) ON DELETE CASCADE,
    sort_order          INTEGER NOT NULL DEFAULT 0,

    registered_name     TEXT DEFAULT '',
    breeders            TEXT DEFAULT '',
    owner_name          TEXT DEFAULT '',
    owner_address       TEXT DEFAULT '',
    owner_email         TEXT DEFAULT '',
    owner_phone         TEXT DEFAULT '',
    call_name           TEXT DEFAULT '',

    photo1_path         TEXT DEFAULT '',        -- portrait / headshot
    photo2_path         TEXT DEFAULT '',        -- action / stack

    pedigree_json       TEXT DEFAULT '{}',      -- {sire, sire_sire, ...}
    dob                 TEXT DEFAULT '',
    color               TEXT DEFAULT '',
    health_json         TEXT DEFAULT '{}',      -- {hips, elbows, eyes, pra, cardiac}

    career_highlights   TEXT DEFAULT '',
    best_virtues        TEXT DEFAULT '',
    wish_list           TEXT DEFAULT '',
    has_produced        TEXT DEFAULT '',

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dogs_kennel ON dogs(kennel_id);

-- Magic-link login tokens (one-time use, short TTL).
CREATE TABLE IF NOT EXISTS magic_links (
    token        TEXT PRIMARY KEY,
    email        TEXT NOT NULL,
    kennel_id    INTEGER,                       -- optional: link straight to an entry
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    used_at      TEXT
);
"""

# JSON columns and how they decode by default (list vs dict).
_KENNEL_JSON = {
    "mentors_json": list, "prominent_json": list, "health_json": dict,
    "venues_json": list, "our_dogs_json": list, "at_stud_json": list,
    "planned_json": list,
}
_DOG_JSON = {"pedigree_json": dict, "health_json": dict}


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# --- Row (de)serialization ---------------------------------------------------
def _decode(row: sqlite3.Row, json_map: dict) -> dict:
    d = dict(row)
    for col, kind in json_map.items():
        raw = d.get(col)
        try:
            d[col] = json.loads(raw) if raw else kind()
        except (json.JSONDecodeError, TypeError):
            d[col] = kind()
    return d


def kennel_from_row(row) -> dict:
    return _decode(row, _KENNEL_JSON) if row else None


def dog_from_row(row) -> dict:
    return _decode(row, _DOG_JSON) if row else None


# --- Kennel CRUD -------------------------------------------------------------
def create_kennel(login_email: str, show_year: int) -> dict:
    now = _now()
    token = new_token()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO kennels (edit_token, login_email, show_year, "
            "created_at, updated_at) VALUES (?,?,?,?,?)",
            (token, login_email.lower(), show_year, now, now),
        )
        new_id = cur.lastrowid
    return get_kennel(new_id)  # read after commit so it's visible


def get_kennel(kennel_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM kennels WHERE id=?", (kennel_id,)
        ).fetchone()
    return kennel_from_row(row)


def get_kennel_by_token(token: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM kennels WHERE edit_token=?", (token,)
        ).fetchone()
    return kennel_from_row(row)


def list_kennels_for_email(email: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM kennels WHERE login_email=? ORDER BY kennel_name",
            (email.lower(),),
        ).fetchall()
    return [kennel_from_row(r) for r in rows]


def list_all_kennels(order_by_name: bool = True) -> list:
    order = "kennel_name COLLATE NOCASE" if order_by_name else "id"
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM kennels ORDER BY {order}").fetchall()
    return [kennel_from_row(r) for r in rows]


def update_kennel(kennel_id: int, fields: dict):
    if not fields:
        return
    # JSON-encode any structured fields passed as python objects.
    encoded = {}
    for k, v in fields.items():
        if k in _KENNEL_JSON and not isinstance(v, str):
            encoded[k] = json.dumps(v)
        else:
            encoded[k] = v
    encoded["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in encoded)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE kennels SET {cols} WHERE id=?",
            (*encoded.values(), kennel_id),
        )


def delete_kennel(kennel_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM kennels WHERE id=?", (kennel_id,))


# --- Dog CRUD ----------------------------------------------------------------
def list_dogs(kennel_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM dogs WHERE kennel_id=? ORDER BY sort_order, id",
            (kennel_id,),
        ).fetchall()
    return [dog_from_row(r) for r in rows]


def count_dogs(kennel_id: int) -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM dogs WHERE kennel_id=?", (kennel_id,)
        ).fetchone()[0]


def get_dog(dog_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM dogs WHERE id=?", (dog_id,)).fetchone()
    return dog_from_row(row)


def create_dog(kennel_id: int) -> dict:
    now = _now()
    with get_conn() as conn:
        nxt = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM dogs WHERE kennel_id=?",
            (kennel_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO dogs (kennel_id, sort_order, created_at, updated_at) "
            "VALUES (?,?,?,?)",
            (kennel_id, nxt, now, now),
        )
        did = cur.lastrowid
    return get_dog(did)  # read after commit so it's visible


def update_dog(dog_id: int, fields: dict):
    if not fields:
        return
    encoded = {}
    for k, v in fields.items():
        if k in _DOG_JSON and not isinstance(v, str):
            encoded[k] = json.dumps(v)
        else:
            encoded[k] = v
    encoded["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in encoded)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE dogs SET {cols} WHERE id=?", (*encoded.values(), dog_id)
        )


def delete_dog(dog_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM dogs WHERE id=?", (dog_id,))


# --- Magic links -------------------------------------------------------------
def create_magic_link(email: str, ttl_min: int, kennel_id: int = None) -> str:
    from datetime import timedelta
    token = new_token(24)
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO magic_links (token, email, kennel_id, created_at, "
            "expires_at) VALUES (?,?,?,?,?)",
            (token, email.lower(), kennel_id, now.isoformat(timespec="seconds"),
             (now + timedelta(minutes=ttl_min)).isoformat(timespec="seconds")),
        )
    return token


def consume_magic_link(token: str) -> dict:
    """Return {email, kennel_id} if valid+unused+unexpired, else None. Marks used."""
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM magic_links WHERE token=?", (token,)
        ).fetchone()
        if not row or row["used_at"]:
            return None
        if datetime.fromisoformat(row["expires_at"]) < now:
            return None
        conn.execute(
            "UPDATE magic_links SET used_at=? WHERE token=?",
            (now.isoformat(timespec="seconds"), token),
        )
        return {"email": row["email"], "kennel_id": row["kennel_id"]}
