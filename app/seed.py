"""
Seed the database with a few realistic **test** kennel + dog entries.

Why this exists: test entries created during an ephemeral session (e.g. a
local dev run that was later thrown away) don't survive into the deployed
database. This command writes real rows into the *active* database — the one
`app.config.DB_PATH` points at — so they appear in the admin panel and are
fully editable/deletable there, exactly like a breeder's own entry.

Usage (inside the running container, against the live volume):

    docker exec essfta-showcase python -m app.seed          # create if absent
    docker exec essfta-showcase python -m app.seed --force  # add another set
    docker exec essfta-showcase python -m app.seed --clear  # remove test rows

Test rows are tagged by a sentinel login-email domain (TEST_DOMAIN) so this
command can find and clean up *only* what it created and never touch real
breeder entries.
"""
import sys

from . import config, db

TEST_DOMAIN = "test.essfta.local"

# Three sample kennels, each with a dog or two, exercising the same fields the
# intake forms collect so they render fully in both the admin list and the book.
_SAMPLE_KENNELS = [
    {
        "kennel": {
            "kennel_name": "Windfall",
            "owner_name": "Test Owner — Alice Windham",
            "location_address": "Ann Arbor, MI",
            "email": f"alice@{TEST_DOMAIN}",
            "phone": "555-0101",
            "year_started": "1998",
            "breeding_philosophy": "Breeding for sound temperament and true "
            "Springer type — sample text so the page renders.",
            "mentors_json": ["Jane Mentor", "Robert Guide"],
            "prominent_json": ["Ch. Windfall's First Light"],
            "health_json": {t: (t in ("Hips", "Eyes", "PRA")) for t in config.HEALTH_TESTS},
            "venues_json": ["Conformation", "Obedience", "Agility"],
            "our_dogs_json": [{"name": "GCh. Windfall Northern Star",
                               "highlights": "Group-placing, multiple BOB."}],
            "at_stud_json": [],
            "planned_json": [],
        },
        "dogs": [
            {
                "registered_name": "GCh. Windfall Northern Star",
                "call_name": "Polaris",
                "breeders": "Alice Windham",
                "owner_name": "Alice Windham",
                "owner_email": f"alice@{TEST_DOMAIN}",
                "dob": "2021-03-14",
                "color": "Liver & White",
                "career_highlights": "BOB at three specialties (sample).",
                "best_virtues": "Effortless side gait; correct coat.",
                "pedigree_json": {"sire": "Ch. Windfall Polestar",
                                  "dam": "Windfall Evening Song"},
                "health_json": {"hips": "OFA Good", "eyes": "CAER clear"},
            },
        ],
    },
    {
        "kennel": {
            "kennel_name": "Briarwood",
            "owner_name": "Test Owner — Ben Brier",
            "location_address": "Portland, OR",
            "email": f"ben@{TEST_DOMAIN}",
            "phone": "555-0102",
            "year_started": "2007",
            "breeding_philosophy": "Dual-purpose field and show lines (sample).",
            "mentors_json": ["Susan Field"],
            "health_json": {t: (t in ("Hips", "Elbows", "Cardiac")) for t in config.HEALTH_TESTS},
            "venues_json": ["Field Trials/Hunt Test", "Conformation", "Scent Work"],
            "at_stud_json": [{"name": "Ch. Briarwood Gunner", "dob": "2020-06-01",
                              "certs": "OFA Good, CAER clear"}],
        },
        "dogs": [
            {
                "registered_name": "Ch. Briarwood Gunner",
                "call_name": "Gunner",
                "breeders": "Ben Brier",
                "dob": "2020-06-01",
                "color": "Black & White",
                "career_highlights": "JH, multiple field placements (sample).",
                "pedigree_json": {"sire": "Ch. Briarwood Ranger",
                                  "dam": "Briarwood Willow"},
                "health_json": {"hips": "OFA Good", "cardiac": "Normal"},
            },
            {
                "registered_name": "Briarwood Autumn Fern",
                "call_name": "Fern",
                "breeders": "Ben Brier",
                "dob": "2022-09-20",
                "color": "Liver & White",
                "best_virtues": "Lovely head, biddable (sample).",
            },
        ],
    },
    {
        "kennel": {
            "kennel_name": "Cedarcrest",
            "owner_name": "Test Owner — Carol Reed",
            "location_address": "Nashua, NH",
            "email": f"carol@{TEST_DOMAIN}",
            "phone": "555-0103",
            "year_started": "2015",
            "breeding_philosophy": "A small hobby kennel; health first (sample).",
            "health_json": {t: (t in ("Hips", "Eyes")) for t in config.HEALTH_TESTS},
            "venues_json": ["Conformation", "Rally", "Therapy"],
            "planned_json": [{"sire_dam": "Cedarcrest Bram x Cedarcrest June",
                              "whelp": "Spring 2026"}],
        },
        "dogs": [],  # a valid entry can start with no dogs yet
    },
]


def _already_seeded() -> list:
    return [k for k in db.list_all_kennels()
            if k["login_email"].endswith(f"@{TEST_DOMAIN}")]


def clear() -> int:
    existing = _already_seeded()
    for k in existing:
        db.delete_kennel(k["id"])  # cascades to dogs via FK ON DELETE CASCADE
    return len(existing)


def seed(force: bool = False) -> list:
    db.init_db()
    if not force and _already_seeded():
        return []
    created = []
    for spec in _SAMPLE_KENNELS:
        login_email = spec["kennel"]["email"]  # own the entry with its test email
        k = db.create_kennel(login_email, config.SHOW_YEAR)
        fields = dict(spec["kennel"])
        fields["status"] = "submitted"
        db.update_kennel(k["id"], fields)
        for dog_spec in spec["dogs"]:
            d = db.create_dog(k["id"])
            db.update_dog(d["id"], dict(dog_spec))
        created.append((k["id"], spec["kennel"]["kennel_name"], len(spec["dogs"])))
    return created


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    db.init_db()
    print(f"Active database: {config.DB_PATH}")

    if "--clear" in argv:
        n = clear()
        print(f"Removed {n} test entr{'y' if n == 1 else 'ies'} "
              f"(login domain @{TEST_DOMAIN}).")
        return

    force = "--force" in argv
    created = seed(force=force)
    if not created:
        n = len(_already_seeded())
        print(f"Test entries already present ({n}). "
              f"Use --force to add another set, or --clear to remove them.")
        return
    print(f"Seeded {len(created)} test entr{'y' if len(created) == 1 else 'ies'}:")
    for kid, name, ndogs in created:
        print(f"  #{kid}  {name}  ({ndogs} dog{'' if ndogs == 1 else 's'})")
    print("They now appear in /admin and open in the normal Open/Edit flow.")


if __name__ == "__main__":
    main()
