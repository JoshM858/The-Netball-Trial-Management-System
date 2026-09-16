"""
Everything to do with trial/player data: CSV storage, CSV export, CSV
bulk import, and the test data generator. Data is stored under data/ as
plain CSV files (trials.csv, players.csv, attendance.csv, rounds.csv,
assignments.csv, users.csv) - one row per record, a header row matching
the column names below.

Running this file directly (`python players.py`) scans this script's own
folder for *.csv files and loads each one into its own trial.
"""

import argparse
import csv
import glob
import hashlib
import json
import os
import random
import shutil
from datetime import datetime

DATA_DIR = "data"
BACKUP_DIR = "backups"

TRIALS_CSV = os.path.join(DATA_DIR, "trials.csv")
PLAYERS_CSV = os.path.join(DATA_DIR, "players.csv")
ATTENDANCE_CSV = os.path.join(DATA_DIR, "attendance.csv")
ROUNDS_CSV = os.path.join(DATA_DIR, "rounds.csv")
ASSIGNMENTS_CSV = os.path.join(DATA_DIR, "assignments.csv")
USERS_CSV = os.path.join(DATA_DIR, "users.csv")

TRIALS_FIELDS = [
    "trial_id", "trial_name", "age_group", "trial_date", "num_courts",
    "min_birth_year", "max_birth_year", "bib_colours_json",
]
PLAYERS_FIELDS = [
    "player_id", "trial_id", "trial_number", "first_name", "last_name", "dob",
    "netball_id", "address", "phone", "email", "parent_name", "parent_phone",
    "parent_email", "playing_history", "position_1", "position_2", "position_3",
]
ATTENDANCE_FIELDS = ["attendance_id", "player_id", "trial_id", "is_present"]
ROUNDS_FIELDS = ["round_id", "trial_id", "round_number", "court_number", "team", "bib_colour"]
ASSIGNMENTS_FIELDS = ["assignment_id", "round_id", "player_id", "position"]
USERS_FIELDS = ["user_id", "username", "password_hash", "salt", "role"]

POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]


def _hash_password(password, salt_hex):
    """Salted SHA-256 hash, used for the default coordinator account."""
    salted = bytes.fromhex(salt_hex) + password.encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def _new_salt():
    return os.urandom(16).hex()


# --------------------------------------------------------------------------- #
# Generic CSV read/write helpers
# --------------------------------------------------------------------------- #

def _read_table(path, int_fields=(), optional_int_fields=()):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for field in int_fields:
            row[field] = int(row[field])
        for field in optional_int_fields:
            row[field] = int(row[field]) if row.get(field) else None
    return rows


def _write_table(path, fieldnames, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                field: ("" if row.get(field) is None else row.get(field, ""))
                for field in fieldnames
            })


def _next_id(rows, id_field):
    if not rows:
        return 1
    return max(row[id_field] for row in rows) + 1


def init_data():
    """Creates data/ and an empty CSV for each table that doesn't exist yet."""
    os.makedirs(DATA_DIR, exist_ok=True)
    for path, fields in (
        (TRIALS_CSV, TRIALS_FIELDS),
        (PLAYERS_CSV, PLAYERS_FIELDS),
        (ATTENDANCE_CSV, ATTENDANCE_FIELDS),
        (ROUNDS_CSV, ROUNDS_FIELDS),
        (ASSIGNMENTS_CSV, ASSIGNMENTS_FIELDS),
        (USERS_CSV, USERS_FIELDS),
    ):
        if not os.path.exists(path):
            _write_table(path, fields, [])

    users = _read_table(USERS_CSV, int_fields=["user_id"])
    if not any(u["role"] == "coordinator" for u in users):
        salt = _new_salt()
        users.append({
            "user_id": _next_id(users, "user_id"),
            "username": "coordinator",
            "password_hash": _hash_password("coordinator123", salt),
            "salt": salt,
            "role": "coordinator",
        })
        _write_table(USERS_CSV, USERS_FIELDS, users)


def backup_data():
    """Copies data/ into backups/ with a timestamped folder name. Returns
    the backup path, or None if there's no data yet to back up."""
    if not os.path.exists(DATA_DIR):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"data_{timestamp}")
    shutil.copytree(DATA_DIR, backup_path)
    return backup_path


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def is_valid_date(date_str):
    try:
        datetime.strptime(date_str.strip(), "%d/%m/%Y")
        return True
    except (ValueError, AttributeError):
        return False


def birth_year_of(dob_str):
    return datetime.strptime(dob_str.strip(), "%d/%m/%Y").year


def check_dob_eligibility(dob_str, min_birth_year, max_birth_year):
    """Checks a DOB against a trial's birth year window. Informational
    only - never blocks registration, since a permit can override it."""
    if not is_valid_date(dob_str):
        return False, "Invalid date format (use DD/MM/YYYY)"
    if min_birth_year is None or max_birth_year is None:
        return True, "No age window set for this trial"
    year = birth_year_of(dob_str)
    if min_birth_year <= year <= max_birth_year:
        return True, f"✓ Valid ({year} is within {min_birth_year}–{max_birth_year})"
    return False, f"⚠ Outside range ({year} not in {min_birth_year}–{max_birth_year}) - permit required"


# --------------------------------------------------------------------------- #
# Trials
# --------------------------------------------------------------------------- #

def _read_trials():
    return _read_table(
        TRIALS_CSV,
        int_fields=["trial_id", "num_courts"],
        optional_int_fields=["min_birth_year", "max_birth_year"],
    )


def create_trial(trial_name, age_group, trial_date, num_courts=1,
                  min_birth_year=None, max_birth_year=None):
    trials = _read_trials()
    trial_id = _next_id(trials, "trial_id")
    trials.append({
        "trial_id": trial_id,
        "trial_name": trial_name,
        "age_group": age_group,
        "trial_date": trial_date,
        "num_courts": num_courts,
        "min_birth_year": min_birth_year,
        "max_birth_year": max_birth_year,
        "bib_colours_json": None,
    })
    _write_table(TRIALS_CSV, TRIALS_FIELDS, trials)
    export_trial_csv(trial_id)


def get_all_trials():
    return sorted(_read_trials(), key=lambda t: t["trial_date"])


def get_trial(trial_id):
    return next((t for t in _read_trials() if t["trial_id"] == trial_id), None)


def update_trial_courts(trial_id, num_courts):
    trials = _read_trials()
    for t in trials:
        if t["trial_id"] == trial_id:
            t["num_courts"] = num_courts
    _write_table(TRIALS_CSV, TRIALS_FIELDS, trials)


def get_trial_bib_colours(trial_id):
    """Returns {court_number: {"A": colour, "B": colour}}, or None if
    nothing's been confirmed yet."""
    trial = get_trial(trial_id)
    if not trial or not trial.get("bib_colours_json"):
        return None
    raw = json.loads(trial["bib_colours_json"])
    return {int(court): teams for court, teams in raw.items()}


def set_trial_bib_colours(trial_id, bib_colours):
    payload = json.dumps({str(court): teams for court, teams in bib_colours.items()})
    trials = _read_trials()
    for t in trials:
        if t["trial_id"] == trial_id:
            t["bib_colours_json"] = payload
    _write_table(TRIALS_CSV, TRIALS_FIELDS, trials)


# --------------------------------------------------------------------------- #
# Players
# --------------------------------------------------------------------------- #

def _read_players():
    return _read_table(PLAYERS_CSV, int_fields=["player_id", "trial_id", "trial_number"])


def get_next_trial_number(trial_id):
    numbers = [p["trial_number"] for p in _read_players() if p["trial_id"] == trial_id]
    return (max(numbers) if numbers else 0) + 1


def create_player(trial_id, first_name, last_name, dob, position_1, position_2,
                   netball_id="", address="", phone="", email="", parent_name="",
                   parent_phone="", parent_email="", playing_history="", position_3=""):
    players = _read_players()
    trial_number = get_next_trial_number(trial_id)
    players.append({
        "player_id": trial_number,
        "trial_id": trial_id,
        "trial_number": trial_number,
        "first_name": first_name,
        "last_name": last_name,
        "dob": dob,
        "netball_id": netball_id,
        "address": address,
        "phone": phone,
        "email": email,
        "parent_name": parent_name,
        "parent_phone": parent_phone,
        "parent_email": parent_email,
        "playing_history": playing_history,
        "position_1": position_1,
        "position_2": position_2,
        "position_3": position_3,
    })
    _write_table(PLAYERS_CSV, PLAYERS_FIELDS, players)
    export_trial_csv(trial_id)
    return trial_number


def get_players_for_trial(trial_id):
    players = [p for p in _read_players() if p["trial_id"] == trial_id]
    return sorted(players, key=lambda p: p["trial_number"])


# --------------------------------------------------------------------------- #
# Attendance / Roll Call
# --------------------------------------------------------------------------- #

def _read_attendance():
    return _read_table(ATTENDANCE_CSV, int_fields=["attendance_id", "player_id", "trial_id", "is_present"])


def set_attendance(player_id, trial_id, is_present):
    attendance = [
        a for a in _read_attendance()
        if not (a["player_id"] == player_id and a["trial_id"] == trial_id)
    ]
    attendance.append({
        "attendance_id": _next_id(attendance, "attendance_id"),
        "player_id": player_id,
        "trial_id": trial_id,
        "is_present": 1 if is_present else 0,
    })
    _write_table(ATTENDANCE_CSV, ATTENDANCE_FIELDS, attendance)


def get_attendance_map(trial_id):
    return {
        a["player_id"]: a["is_present"]
        for a in _read_attendance() if a["trial_id"] == trial_id
    }


def get_present_players(trial_id):
    present_ids = {
        a["player_id"] for a in _read_attendance()
        if a["trial_id"] == trial_id and a["is_present"] == 1
    }
    players = [p for p in _read_players() if p["trial_id"] == trial_id and p["player_id"] in present_ids]
    return sorted(players, key=lambda p: p["trial_number"])


# --------------------------------------------------------------------------- #
# Rounds & Assignments
# --------------------------------------------------------------------------- #

def _read_rounds():
    return _read_table(ROUNDS_CSV, int_fields=["round_id", "trial_id", "round_number", "court_number"])


def _read_assignments():
    return _read_table(ASSIGNMENTS_CSV, int_fields=["assignment_id", "round_id", "player_id"])


def clear_rounds_for_trial(trial_id):
    rounds = _read_rounds()
    round_ids = {r["round_id"] for r in rounds if r["trial_id"] == trial_id}

    remaining_rounds = [r for r in rounds if r["trial_id"] != trial_id]
    remaining_assignments = [a for a in _read_assignments() if a["round_id"] not in round_ids]

    _write_table(ROUNDS_CSV, ROUNDS_FIELDS, remaining_rounds)
    _write_table(ASSIGNMENTS_CSV, ASSIGNMENTS_FIELDS, remaining_assignments)


def create_round_entry(trial_id, round_number, court_number, team, bib_colour):
    rounds = _read_rounds()
    round_id = _next_id(rounds, "round_id")
    rounds.append({
        "round_id": round_id,
        "trial_id": trial_id,
        "round_number": round_number,
        "court_number": court_number,
        "team": team,
        "bib_colour": bib_colour,
    })
    _write_table(ROUNDS_CSV, ROUNDS_FIELDS, rounds)
    return round_id


def create_assignment(round_id, player_id, position):
    assignments = _read_assignments()
    assignments.append({
        "assignment_id": _next_id(assignments, "assignment_id"),
        "round_id": round_id,
        "player_id": player_id,
        "position": position,
    })
    _write_table(ASSIGNMENTS_CSV, ASSIGNMENTS_FIELDS, assignments)


def get_rounds_for_trial(trial_id):
    rounds = [r for r in _read_rounds() if r["trial_id"] == trial_id]
    return sorted(rounds, key=lambda r: (r["round_number"], r["court_number"], r["team"]))


def get_assignments_for_round(round_id):
    round_row = next((r for r in _read_rounds() if r["round_id"] == round_id), None)
    trial_id = round_row["trial_id"] if round_row else None
    players_by_id = {
        p["player_id"]: p for p in _read_players()
        if trial_id is None or p["trial_id"] == trial_id
    }
    rows = []
    for a in _read_assignments():
        if a["round_id"] != round_id:
            continue
        player = players_by_id.get(a["player_id"], {})
        row = dict(a)
        row["first_name"] = player.get("first_name", "")
        row["last_name"] = player.get("last_name", "")
        row["trial_number"] = player.get("trial_number", "")
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #

def _read_users():
    return _read_table(USERS_CSV, int_fields=["user_id"])


def create_user(username, password_hash, role, salt=""):
    users = _read_users()
    users.append({
        "user_id": _next_id(users, "user_id"),
        "username": username,
        "password_hash": password_hash,
        "salt": salt,
        "role": role,
    })
    _write_table(USERS_CSV, USERS_FIELDS, users)


def get_user_by_username(username):
    return next((u for u in _read_users() if u["username"] == username), None)


# --------------------------------------------------------------------------- #
# CSV export - clean player register, for the Export tab
# --------------------------------------------------------------------------- #

CSV_HEADERS = ["Trial No", "First Name", "Last Name", "DOB", "Position 1", "Position 2"]

PLAYER_FIELD_ORDER = ["trial_number", "first_name", "last_name", "dob", "position_1", "position_2"]


def export_players_csv(players, filepath):
    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for p in players:
            row = [p.get(field, "") for field in PLAYER_FIELD_ORDER]
            writer.writerow(row)

    return filepath


EXPORTS_DIR = "exports"


def export_trial_csv(trial_id):
    """Writes/updates exports/<trial name>_players.csv for this trial.
    Called automatically whenever a trial is created or a player is added,
    so there's always an up-to-date CSV on disk without needing to press
    the Export tab's button."""
    trial = get_trial(trial_id)
    if not trial:
        return None
    safe_name = trial["trial_name"].replace(" ", "_") or f"trial_{trial_id}"
    filepath = os.path.join(EXPORTS_DIR, f"{safe_name}_players.csv")
    return export_players_csv(get_players_for_trial(trial_id), filepath)


# --------------------------------------------------------------------------- #
# CSV import / bulk seeding
# --------------------------------------------------------------------------- #
# Auto-detects two formats: the clean format export_players_csv() writes
# (has a header row), and a raw format matching a full registration export
# (no header, blank trial number, one combined full-name field) in this
# column order:
#     (blank), Full Name, DOB, Netball ID, Address, Phone, Email,
#     Parent Name, Parent Phone, Parent Email, Playing History,
#     Position 1, Position 2, Position 3 (optional)

RAW_COLUMNS = [
    "trial_no", "full_name", "dob", "netball_id", "address", "phone", "email",
    "parent_name", "parent_phone", "parent_email", "playing_history",
    "position_1", "position_2", "position_3",
]

def find_csv_files():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return sorted(glob.glob(os.path.join(script_dir, "*.csv")))


def _read_rows(filepath):
    with open(filepath, newline="", encoding="utf-8") as f:
        return [row for row in csv.reader(f) if row and any(cell.strip() for cell in row)]


def detect_format(rows):
    if not rows:
        return "raw"
    first_row = [cell.strip() for cell in rows[0]]
    if first_row[:len(CSV_HEADERS)] == CSV_HEADERS:
        return "clean"
    return "raw"


def split_full_name(full_name):
    full_name = full_name.strip()
    if " " not in full_name:
        return full_name, ""
    first, last = full_name.split(" ", 1)
    return first, last


def parse_clean_rows(rows):
    players = []
    for row in rows[1:]:
        if len(row) < 6:
            continue
        players.append({
            "first_name": row[1].strip(),
            "last_name": row[2].strip(),
            "dob": row[3].strip(),
            "position_1": row[4].strip(),
            "position_2": row[5].strip(),
        })
    return players


def parse_raw_rows(rows):
    start_index = 0
    if rows and len(rows[0]) > 2 and not is_valid_date(rows[0][2].strip()):
        start_index = 1

    players = []
    for row in rows[start_index:]:
        if len(row) < 13:
            continue

        full_name = row[1].strip()
        first_name, last_name = split_full_name(full_name)

        players.append({
            "first_name": first_name,
            "last_name": last_name,
            "dob": row[2].strip(),
            "netball_id": row[3].strip(),
            "address": row[4].strip(),
            "phone": row[5].strip(),
            "email": row[6].strip(),
            "parent_name": row[7].strip(),
            "parent_phone": row[8].strip(),
            "parent_email": row[9].strip(),
            "playing_history": row[10].strip(),
            "position_1": row[11].strip(),
            "position_2": row[12].strip(),
            "position_3": row[13].strip() if len(row) > 13 else "",
        })
    return players


def load_csv(filepath):
    rows = _read_rows(filepath)
    fmt = detect_format(rows)
    if fmt == "clean":
        return parse_clean_rows(rows), fmt
    return parse_raw_rows(rows), fmt


def trial_name_from_filename(filepath):
    return os.path.splitext(os.path.basename(filepath))[0]


def get_or_create_trial(trial_name, age_group, trial_date, num_courts):
    existing = next((t for t in get_all_trials() if t["trial_name"] == trial_name), None)
    if existing:
        return existing["trial_id"], False

    create_trial(trial_name, age_group, trial_date, num_courts)
    new_trial = next(t for t in get_all_trials() if t["trial_name"] == trial_name)
    return new_trial["trial_id"], True


def _prompt_for_position(field_label, invalid_value, player_label):
    """A position outside the 7 real netball positions (e.g. a code from a
    different sport's CSV pasted into the wrong columns) can never be
    satisfied by the rotation algorithm - that player would sit out every
    round and the round count would climb to the safety cap chasing a
    guarantee that can't be met. Rather than silently dropping the row,
    asks the coordinator what it was actually meant to be. Returns the
    corrected position, or None if they choose to skip this player."""
    print(f"  {player_label}: {field_label} is {invalid_value!r}, not a netball position.")
    valid_list = ", ".join(POSITIONS)
    while True:
        answer = input(
            f"    Correct {field_label} for {player_label} ({valid_list}), "
            f"or leave blank to skip this player: "
        ).strip().upper()
        if not answer:
            return None
        if answer in POSITIONS:
            return answer
        print(f"    '{answer}' isn't one of {valid_list} - try again.")


def seed_from_csv(filepath, trial_date, num_courts):
    trial_name = trial_name_from_filename(filepath)
    age_group = trial_name

    try:
        players, fmt = load_csv(filepath)
    except (OSError, csv.Error) as e:
        print(f"{os.path.basename(filepath)}: skipped - could not read file ({e})")
        return 0, 0

    trial_id, created = get_or_create_trial(trial_name, age_group, trial_date, num_courts)
    status = "created" if created else "existing"

    # Importing into a trial that already has players (e.g. re-running the
    # import, or a CSV that overlaps with test data already loaded) used to
    # just append everyone again, doubling the roster. Skip anyone who
    # already matches an existing player by netball ID, or by name + DOB.
    existing = get_players_for_trial(trial_id)
    seen_netball_ids = {p["netball_id"] for p in existing if p["netball_id"]}
    seen_name_dobs = {
        (p["first_name"].strip().lower(), p["last_name"].strip().lower(), p["dob"])
        for p in existing
    }

    loaded = 0
    skipped = 0
    duplicates = 0
    bad_positions = 0
    for p in players:
        if not p["first_name"] or not p["last_name"]:
            skipped += 1
            continue
        if not is_valid_date(p["dob"]):
            skipped += 1
            continue

        position_1 = p["position_1"]
        position_2 = p["position_2"]
        player_label = f"{p['first_name']} {p['last_name']} (DOB {p['dob']})"
        if position_1 not in POSITIONS:
            position_1 = _prompt_for_position("Position 1", position_1, player_label)
        if position_1 is not None and position_2 not in POSITIONS:
            position_2 = _prompt_for_position("Position 2", position_2, player_label)
        if position_1 is None or position_2 is None:
            bad_positions += 1
            continue

        netball_id = p.get("netball_id", "")
        name_dob = (p["first_name"].strip().lower(), p["last_name"].strip().lower(), p["dob"])
        if (netball_id and netball_id in seen_netball_ids) or name_dob in seen_name_dobs:
            duplicates += 1
            continue

        create_player(
            trial_id, p["first_name"], p["last_name"], p["dob"],
            position_1, position_2,
            netball_id=netball_id,
            address=p.get("address", ""),
            phone=p.get("phone", ""),
            email=p.get("email", ""),
            parent_name=p.get("parent_name", ""),
            parent_phone=p.get("parent_phone", ""),
            parent_email=p.get("parent_email", ""),
            playing_history=p.get("playing_history", ""),
            position_3=p.get("position_3", ""),
        )
        if netball_id:
            seen_netball_ids.add(netball_id)
        seen_name_dobs.add(name_dob)
        loaded += 1

    print(f"{os.path.basename(filepath)} [{fmt} format]: {status} trial '{trial_name}' "
          f"(id {trial_id}) - loaded {loaded}/{len(players)} players "
          f"({skipped} skipped, {duplicates} already registered in this trial, "
          f"{bad_positions} skipped after an unresolved non-netball position)")
    return loaded, skipped + duplicates + bad_positions


def prompt_for_shared_settings(args):
    if not args.date:
        args.date = input("Trial date for all trials (DD/MM/YYYY): ").strip()
    if not args.courts:
        courts_input = input("Number of courts for all trials [1]: ").strip()
        args.courts = int(courts_input) if courts_input else 1
    return args


def main():
    parser = argparse.ArgumentParser(
        description="Scans this script's folder for CSV files and loads each one into its "
                     "own trial (named after the file)."
    )
    parser.add_argument("--date", default=None, help="Trial date applied to every CSV, DD/MM/YYYY")
    parser.add_argument("--courts", type=int, default=None,
                         help="Number of courts applied to every CSV (defaults to 1)")
    args = parser.parse_args()

    csv_files = find_csv_files()
    if not csv_files:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"No CSV files found in {script_dir} - nothing to load.")
        return

    print(f"Found {len(csv_files)} CSV file(s): {', '.join(os.path.basename(f) for f in csv_files)}")
    args = prompt_for_shared_settings(args)

    init_data()

    total_loaded = 0
    total_skipped = 0
    for filepath in csv_files:
        loaded, skipped = seed_from_csv(filepath, args.date, args.courts)
        total_loaded += loaded
        total_skipped += skipped

    print(f"\nDone - {total_loaded} player(s) loaded across {len(csv_files)} file(s), "
          f"{total_skipped} row(s) skipped.")


# --------------------------------------------------------------------------- #
# Test data generation
# --------------------------------------------------------------------------- #

FIRST_NAMES = [
    "Emma", "Sophie", "Sarah", "Lena", "Aisha", "Mia", "Chloe", "Priya", "Lucy", "Amy",
    "Grace", "Zoe", "Ella", "Jade", "Olivia", "Isla", "Ruby", "Charlotte", "Ava", "Mia",
    "Willow", "Freya", "Harper", "Lily", "Matilda", "Zara", "Layla", "Maya", "Ivy", "Chelsea",
    "Georgia", "Holly", "Amelia", "Sienna", "Poppy", "Eve", "Bella", "Hannah", "Alicia", "Nina",
]

LAST_NAMES = [
    "Nguyen", "Tran", "Mohammed", "Park", "Ahmed", "Kovac", "Pham", "Sharma", "Tan", "Chen",
    "Wilson", "Brown", "Kowalski", "Robinson", "Smith", "Taylor", "Walker", "White", "Green",
    "Baker", "Hill", "King", "Scott", "Adams", "Nelson", "Carter", "Mitchell", "Roberts", "Turner",
    "Phillips", "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart", "Morris", "Rogers",
    "Reed", "Cook",
]


def _random_dob():
    year = random.choice([2013, 2014])
    day = random.randint(1, 28)
    month = random.randint(1, 12)
    return f"{day:02d}/{month:02d}/{year}"


def _random_positions():
    pos1 = random.choice(POSITIONS)
    pos2 = random.choice([p for p in POSITIONS if p != pos1])
    return pos1, pos2


def generate_test_players(count=100):
    random.seed(42)
    players = []
    for _ in range(count):
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        dob = _random_dob()
        pos1, pos2 = _random_positions()
        players.append((first_name, last_name, dob, pos1, pos2))
    return players


def load_test_players(count=100):
    trial_name = f"Test Trial ({count})"
    trials = get_all_trials()
    existing = next((t for t in trials if t["trial_name"] == trial_name), None)

    if existing:
        trial_id = existing["trial_id"]
        print(f"Using existing trial: {trial_name} (id {trial_id})")
    else:
        create_trial(trial_name, "U13", "01/09/2026")
        trial_id = next(t["trial_id"] for t in get_all_trials() if t["trial_name"] == trial_name)
        print(f"Created new trial '{trial_name}' (id {trial_id})")

    players = generate_test_players(count)
    for first_name, last_name, dob, pos1, pos2 in players:
        trial_number = create_player(trial_id, first_name, last_name, dob, pos1, pos2)
        print(f"  #{trial_number} {first_name} {last_name} ({pos1}/{pos2})")

    print(f"\nDone - {len(players)} test players added to trial id {trial_id}.")


if __name__ == "__main__":
    main()
