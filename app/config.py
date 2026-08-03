"""
ESSFTA Foundation Breeders' Showcase — configuration, brand palette, and field definitions.

The field definitions here are the single source of truth for both the intake
forms and the assembled booklet, so the two can never drift out of sync.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

# --- Paths -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SHOWCASE_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = Path(os.environ.get("SHOWCASE_UPLOAD_DIR", BASE_DIR / "uploads"))
DB_PATH = DATA_DIR / "showcase.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# --- App ---------------------------------------------------------------------
SECRET_KEY = os.environ.get("SHOWCASE_SECRET_KEY", "dev-insecure-change-me")
BASE_URL = os.environ.get("SHOWCASE_BASE_URL", "http://localhost:8790")
SHOW_YEAR = int(os.environ.get("SHOWCASE_YEAR", "2026"))
MAGIC_LINK_TTL_MIN = 60  # magic links valid for 60 minutes

# Admins (comma-separated emails) who can edit any kennel + assemble the book.
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get(
        "SHOWCASE_ADMIN_EMAILS", "collverab3@gmail.com"
    ).split(",")
    if e.strip()
}

# --- Entry deadline ----------------------------------------------------------
# Breeders may not create or change an entry after this instant; they can still
# sign in and read what they submitted. Admins are never locked out, so they can
# still fix a typo or enter someone on request.
#
# Default = end of day 16 September 2026, Pacific time. Pacific (rather than the
# server's UTC) so that nobody in the continental US is cut off early, and the
# National itself is in Albany, Oregon. Override with an ISO-8601 datetime in
# SHOWCASE_ENTRY_DEADLINE, e.g. "2026-09-16T23:59:59-05:00".
ENTRY_DEADLINE = datetime.fromisoformat(
    os.environ.get("SHOWCASE_ENTRY_DEADLINE", "2026-09-16T23:59:59-07:00")
)
if ENTRY_DEADLINE.tzinfo is None:  # a naive override would break the comparison
    ENTRY_DEADLINE = ENTRY_DEADLINE.replace(tzinfo=timezone.utc)

# --- Mailgun (magic-link delivery) ------------------------------------------
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN", "mg.collver.biz")
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY", "")
MAIL_FROM = os.environ.get(
    "SHOWCASE_MAIL_FROM", "ESSFTA Foundation Breeders Showcase <showcase@collver.biz>"
)

# --- Brand palette (ESSFTA 100th Anniversary 1926–2026) ----------------------
# Sampled from the centennial banner: deep forest green, gold, cream.
PALETTE = {
    "green_dark": "#0d3b23",
    "green": "#15532f",
    "green_soft": "#2a6b45",
    "gold": "#c8a53a",
    "gold_dark": "#a8862a",
    "cream": "#f6f1e2",
    "ink": "#26251f",
    "paper": "#ffffff",
}

# --- Limits (from the paper forms) ------------------------------------------
MAX_DOGS_PER_KENNEL = 3        # full dog pages w/ photos
MAX_MENTORS = 3
MAX_PROMINENT_KENNELS = 4
MAX_OUR_DOGS = 4               # text list on the kennel page
MAX_AT_STUD = 2
MAX_PLANNED_BREEDINGS = 2
PHOTOS_PER_DOG = 2

# --- Kennel page: health testing checkboxes ---------------------------------
HEALTH_TESTS = ["Hips", "Elbows", "Eyes", "PRA", "Cardiac"]

# --- Kennel page: venue checkboxes ------------------------------------------
VENUES = [
    "Agility", "Barn Hunt", "Canine Good Citizen", "Conformation",
    "Coursing Ability/FastCAT", "Dock Diving", "FIT Dog",
    "Field Trials/Hunt Test", "Obedience", "Rally", "Scent Work",
    "Therapy", "Tracking", "Trick Dog", "Working Dog",
]

# --- Dog page: health clearance number fields --------------------------------
DOG_HEALTH_FIELDS = [
    ("hips", "Hips #"),
    ("elbows", "Elbows #"),
    ("eyes", "Eyes #"),
    ("pra", "PRA"),
    ("cardiac", "Cardiac #"),
    ("chic", "CHIC #"),
]

# --- Dog page: 3-generation pedigree slots -----------------------------------
# The subject dog sits at the root (its registered name); these are the 6
# ancestor slots that branch out to sire/dam and the four grandparents.
PEDIGREE_SLOTS = [
    ("sire", "Sire"),
    ("sire_sire", "Sire's Sire"),
    ("sire_dam", "Sire's Dam"),
    ("dam", "Dam"),
    ("dam_sire", "Dam's Sire"),
    ("dam_dam", "Dam's Dam"),
]

# Max upload size per photo (bytes) after client-side resize.
MAX_PHOTO_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
