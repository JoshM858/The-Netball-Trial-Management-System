"""
Everything to do with trial/player data: CSV storage, CSV export, CSV
bulk import, and the test data generator.

Storage layout under data/:
    data/trials.csv                        - one row per trial (index)
    data/users.csv                         - login accounts
    data/<Trial>_<Date>/<Trial>_<Date>_Players.csv
    data/<Trial>_<Date>/<Trial>_<Date>_Attendance.csv
    data/<Trial>_<Date>/<Trial>_<Date>_Rounds.csv
    data/<Trial>_<Date>/<Trial>_<Date>_Assignments.csv

Each trial gets its own folder (e.g. "U17_11-09-2026") so its players,
roll call, and rounds are easy to find and read on their own, rather than
every trial's rows being mixed together in one shared file.

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
import re
import shutil
from datetime import datetime

# Folder holding all the CSV files. Plain CSV files in one folder, not a database: the club
# can open them in Excel, and copying this one folder is a complete backup.
DATA_DIR = "data"
# Folder where dated copies of data/ are kept
BACKUP_DIR = "backups"

# One index file lists every trial. Each trial's players, roll call and rounds go in their
# own folder (see _trial_dir), so one trial is easy to find and read on its own.
TRIALS_CSV = os.path.join(DATA_DIR, "trials.csv")
# Login accounts are in their own CSV, away from the player data. Only salted hashes are
# stored here, never the passwords themselves.
USERS_CSV = os.path.join(DATA_DIR, "users.csv")

# Column names of each CSV file, in the order they are written; the first column is its id.
# Each is a list, not a set or dictionary, because a CSV needs its columns in a fixed order.
# The same list writes the header row and picks each row's values.
TRIALS_FIELDS = [
    "trial_id", "trial_name", "age_group", "trial_date", "num_courts",
    "min_birth_year", "max_birth_year", "bib_colours_json",
]
# dob, phone and parent_phone are kept as text. A phone number starts with 0 and a number
# type would drop it. dob is typed and shown as DD/MM/YYYY, so it stays as that text.
PLAYERS_FIELDS = [
    "player_id", "trial_id", "trial_number", "first_name", "last_name", "dob",
    "netball_id", "address", "phone", "email", "parent_name", "parent_phone",
    "parent_email", "playing_history", "position_1", "position_2", "position_3",
]
# is_present is 1 or 0, not True or False, because a CSV cell holds text and the roll call
# tick box reads and writes 1 or 0.
ATTENDANCE_FIELDS = ["attendance_id", "player_id", "trial_id", "is_present"]
ROUNDS_FIELDS = ["round_id", "trial_id", "round_number", "court_number", "team", "bib_colour"]
ASSIGNMENTS_FIELDS = ["assignment_id", "round_id", "player_id", "position"]
USERS_FIELDS = ["user_id", "username", "password_hash", "salt", "role"]

# The seven netball positions, as text codes because that is what the club writes down. A list
# keeps court order GS to GK, and `x in POSITIONS` checks that a typed position is real.
POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]


def _hash_password(password, salt_hex):
    """Salted SHA-256 hash, used for the default coordinator account."""
    salted = bytes.fromhex(salt_hex) + password.encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def _new_salt():
    """Returns a random 16-byte salt as 32 hex characters."""
    return os.urandom(16).hex()


# --------------------------------------------------------------------------- #
# Generic CSV read/write helpers
# --------------------------------------------------------------------------- #

def _read_table(path, int_fields=(), optional_int_fields=()):
    """Reads a CSV file into a list of dicts. Columns in int_fields become whole numbers;
    optional_int_fields become a number or None if blank. Returns [] if the file is missing."""
    # A missing file is treated as an empty table
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        # Every row is a dict of text; the loops below turn the number columns into ints
        rows = list(csv.DictReader(f))
    # Convert the number columns of every row from text to int (a blank optional one becomes None)
    for row in rows:
        for field in int_fields:
            row[field] = int(row[field])
        for field in optional_int_fields:
            row[field] = int(row[field]) if row.get(field) else None
    return rows


def _write_table(path, fieldnames, rows):
    """Writes a list of dicts to a CSV file in the column order given, making the folder if
    needed. None is written as an empty cell."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        # DictWriter writes each dict in the column order given by fieldnames
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        # One line per row; None is written as an empty cell
        for row in rows:
            writer.writerow({
                field: ("" if row.get(field) is None else row.get(field, ""))
                for field in fieldnames
            })


def _next_id(rows, id_field):
    """Returns the next unused id: one more than the biggest existing id (1 if there are none)."""
    # An empty table starts at id 1
    if not rows:
        return 1
    # One more than the biggest id, so ids are never reused
    return max(row[id_field] for row in rows) + 1


def _safe_slug(text):
    """Turns a trial name or date into something safe to use in a folder/
    file name - slashes become dashes, spaces become underscores, and
    anything else that isn't a letter/digit/dash/underscore is dropped."""
    text = text.strip().replace("/", "-").replace(" ", "_")
    return "".join(ch for ch in text if ch.isalnum() or ch in "-_")


def _trial_folder_name(trial):
    """e.g. trial_name="U17", trial_date="11/09/2026" -> "U17_11-09-2026"."""
    return f"{_safe_slug(trial['trial_name'])}_{_safe_slug(trial['trial_date'])}"


def _trial_dir(trial):
    """Returns the folder that holds this trial's own CSV files."""
    return os.path.join(DATA_DIR, _trial_folder_name(trial))


def _trial_file(trial, label):
    """Full path to one of this trial's own CSVs, e.g. label="Attendance"
    -> data/U17_11-09-2026/U17_11-09-2026_Attendance.csv."""
    folder = _trial_folder_name(trial)
    return os.path.join(_trial_dir(trial), f"{folder}_{label}.csv")


def init_data():
    """Creates data/ and an empty CSV for the trial index / accounts if
    they don't exist yet. Each trial's own Players/Attendance/Rounds/
    Assignments files live in that trial's own folder instead - see
    create_trial()."""
    os.makedirs(DATA_DIR, exist_ok=True)
    # Create each index file with only its header row if it is not there yet
    for path, fields in (
        (TRIALS_CSV, TRIALS_FIELDS),
        (USERS_CSV, USERS_FIELDS),
    ):
        if not os.path.exists(path):
            _write_table(path, fields, [])

    # Existing accounts; the default coordinator is only added if there is none yet
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


# A complete backup is just a copy of the data folder, because that folder holds every CSV
# there is. The date and time in the name means an old backup is never overwritten.
def backup_data():
    """Copies data/ into backups/ with a timestamped folder name. Returns
    the backup path, or None if there's no data yet to back up."""
    # Nothing to back up before the data folder exists
    if not os.path.exists(DATA_DIR):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    # e.g. 20260917_101530_123456 - the microseconds stop two backups in the same second sharing a name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = os.path.join(BACKUP_DIR, f"data_{timestamp}")
    shutil.copytree(DATA_DIR, backup_path)
    return backup_path


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def is_valid_date(date_str):
    """Returns True if the text is a real date written DD/MM/YYYY (31/02/2026 is not)."""
    # strptime raises ValueError for a date that is not real or not DD/MM/YYYY (AttributeError if not text)
    try:
        datetime.strptime(date_str.strip(), "%d/%m/%Y")
        return True
    except (ValueError, AttributeError):
        return False


def birth_year_of(dob_str):
    """Returns the year part of a DD/MM/YYYY date of birth."""
    return datetime.strptime(dob_str.strip(), "%d/%m/%Y").year


def is_future_date(date_str):
    """Returns True if the DD/MM/YYYY date is after today (a date of birth can't be in the future)."""
    return datetime.strptime(date_str.strip(), "%d/%m/%Y").date() > datetime.now().date()


def is_valid_phone(text):
    """Returns True for an Australian phone number. Spaces, brackets and hyphens are
    ignored, so 0412 345 678, (03) 9876 5432 and +61 412 345 678 are all accepted."""
    # Keep only the digits and a leading + so the layout the person typed does not matter
    cleaned = re.sub(r"[\s()\-]", "", text or "")
    # A leading 0 or +61 followed by nine digits (area or mobile code, then the number)
    return re.fullmatch(r"(?:0|\+61)\d{9}", cleaned) is not None


def is_valid_email(text):
    """Returns True if the text looks like name@domain.ext (one @, no spaces, a dot after it)."""
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", (text or "").strip()) is not None


def check_dob_eligibility(dob_str, min_birth_year, max_birth_year):
    """Checks a DOB against a trial's birth year window. Informational
    only - never blocks registration, since a permit can override it."""
    # Type check first: the year can't be read from a bad date
    if not is_valid_date(dob_str):
        return False, "Invalid date format (use DD/MM/YYYY)"
    # No window set for the trial: every date of birth is accepted
    if min_birth_year is None or max_birth_year is None:
        return True, "No age window set for this trial"
    # Only the birth year matters for the age window
    year = birth_year_of(dob_str)
    # Range check: the birth year must be inside the window (both ends included)
    if min_birth_year <= year <= max_birth_year:
        return True, f"✓ Valid ({year} is within {min_birth_year}–{max_birth_year})"
    return False, f"⚠ Outside range ({year} not in {min_birth_year}–{max_birth_year}) - permit required"


# --------------------------------------------------------------------------- #
# Trials
# --------------------------------------------------------------------------- #

def _read_trials():
    """Reads every trial from trials.csv (ids and courts as numbers, birth years as number or None)."""
    return _read_table(
        TRIALS_CSV,
        int_fields=["trial_id", "num_courts"],
        optional_int_fields=["min_birth_year", "max_birth_year"],
    )


def create_trial(trial_name, age_group, trial_date, num_courts=1,
                  min_birth_year=None, max_birth_year=None):
    """Adds a trial to trials.csv, makes its own folder with empty Players, Attendance, Rounds
    and Assignments files, and writes its player export."""
    trials = _read_trials()
    trial_id = _next_id(trials, "trial_id")
    # One row for trials.csv; bib_colours_json stays empty until Round Settings is saved
    trial_row = {
        "trial_id": trial_id,
        "trial_name": trial_name,
        "age_group": age_group,
        "trial_date": trial_date,
        "num_courts": num_courts,
        "min_birth_year": min_birth_year,
        "max_birth_year": max_birth_year,
        "bib_colours_json": None,
    }
    trials.append(trial_row)
    _write_table(TRIALS_CSV, TRIALS_FIELDS, trials)

    # Sets up this trial's own folder (e.g. data/U17_11-09-2026/) with an
    # empty Players/Attendance/Rounds/Assignments CSV each, so the folder
    # is there to look at immediately, even before anyone's registered.
    for fields, label in (
        (PLAYERS_FIELDS, "Players"),
        (ATTENDANCE_FIELDS, "Attendance"),
        (ROUNDS_FIELDS, "Rounds"),
        (ASSIGNMENTS_FIELDS, "Assignments"),
    ):
        _write_table(_trial_file(trial_row, label), fields, [])

    export_trial_csv(trial_id)


def get_all_trials():
    """Returns every trial, sorted by date with the soonest first."""
    # Sorted by the real date (the text would put 05/10 before 11/09); a bad date sorts last
    return sorted(_read_trials(), key=lambda t: datetime.strptime(t["trial_date"], "%d/%m/%Y") if is_valid_date(t["trial_date"]) else datetime.max)


def get_trial(trial_id):
    """Returns the trial with this id as a dict, or None if it does not exist."""
    return next((t for t in _read_trials() if t["trial_id"] == trial_id), None)


def update_trial_courts(trial_id, num_courts):
    """Changes the number of courts for one trial."""
    trials = _read_trials()
    # Find the trial with this id and change its number of courts
    for t in trials:
        if t["trial_id"] == trial_id:
            t["num_courts"] = num_courts
    _write_table(TRIALS_CSV, TRIALS_FIELDS, trials)


def get_trial_bib_colours(trial_id):
    """Returns {court_number: {"A": colour, "B": colour}}, or None if
    nothing's been confirmed yet."""
    trial = get_trial(trial_id)
    # No trial, or no colours saved yet
    if not trial or not trial.get("bib_colours_json"):
        return None
    raw = json.loads(trial["bib_colours_json"])
    return {int(court): teams for court, teams in raw.items()}


# Bib colours are a dictionary inside a dictionary (court -> team -> colour), which won't fit
# in one CSV cell. So they are saved as JSON text in one cell of trials.csv: no extra file for
# a few words, and json.loads() gives the dictionary back. JSON turns the court numbers into
# text, so get_trial_bib_colours() turns them back into whole numbers.
def set_trial_bib_colours(trial_id, bib_colours):
    """Saves the bib colours for a trial as JSON text: {court: {"A": colour, "B": colour}}."""
    payload = json.dumps({str(court): teams for court, teams in bib_colours.items()})
    trials = _read_trials()
    # Find the trial with this id and store the JSON text on it
    for t in trials:
        if t["trial_id"] == trial_id:
            t["bib_colours_json"] = payload
    _write_table(TRIALS_CSV, TRIALS_FIELDS, trials)


# --------------------------------------------------------------------------- #
# Players
# --------------------------------------------------------------------------- #

def _read_players(trial_id):
    """Reads the Players file for one trial ([] if the trial does not exist)."""
    trial = get_trial(trial_id)
    # An unknown trial id has no file to read
    if not trial:
        return []
    return _read_table(_trial_file(trial, "Players"), int_fields=["player_id", "trial_id", "trial_number"])


def _write_players(trial_id, rows):
    """Writes the Players file for one trial."""
    trial = get_trial(trial_id)
    # Only write if the trial exists (the file path is built from the trial)
    if trial:
        _write_table(_trial_file(trial, "Players"), PLAYERS_FIELDS, rows)


def get_next_trial_number(trial_id):
    """Returns the number the next registered player will wear (highest so far + 1)."""
    numbers = [p["trial_number"] for p in _read_players(trial_id)]
    return (max(numbers) if numbers else 0) + 1


def create_player(trial_id, first_name, last_name, dob, position_1, position_2,
                   netball_id="", address="", phone="", email="", parent_name="",
                   parent_phone="", parent_email="", playing_history="", position_3=""):
    """Adds a player to a trial, updates the export CSV and returns the player's trial number.
    Only the first five details are needed; the rest default to blank."""
    players = _read_players(trial_id)
    trial_number = get_next_trial_number(trial_id)
    # player_id is the trial number because each trial has its own Players file
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
    _write_players(trial_id, players)
    export_trial_csv(trial_id)
    return trial_number


def get_players_for_trial(trial_id):
    """Returns a trial's players sorted by trial number."""
    return sorted(_read_players(trial_id), key=lambda p: p["trial_number"])


# --------------------------------------------------------------------------- #
# Attendance / Roll Call
# --------------------------------------------------------------------------- #

def _read_attendance(trial_id):
    """Reads the Attendance file for one trial."""
    trial = get_trial(trial_id)
    # An unknown trial id has no file to read
    if not trial:
        return []
    return _read_table(
        _trial_file(trial, "Attendance"),
        int_fields=["attendance_id", "player_id", "trial_id", "is_present"],
    )


def _write_attendance(trial_id, rows):
    """Writes the Attendance file for one trial."""
    trial = get_trial(trial_id)
    # Only write if the trial exists (the file path is built from the trial)
    if trial:
        _write_table(_trial_file(trial, "Attendance"), ATTENDANCE_FIELDS, rows)


def set_attendance(player_id, trial_id, is_present):
    """Records whether one player is present (replacing any earlier row for that player)."""
    # Drop this player's old row first so there is only ever one row per player
    attendance = [a for a in _read_attendance(trial_id) if a["player_id"] != player_id]
    attendance.append({
        "attendance_id": _next_id(attendance, "attendance_id"),
        "player_id": player_id,
        "trial_id": trial_id,
        "is_present": 1 if is_present else 0,
    })
    _write_attendance(trial_id, attendance)


def get_attendance_map(trial_id):
    """Returns {player_id: 1 or 0} from the saved roll call."""
    return {a["player_id"]: a["is_present"] for a in _read_attendance(trial_id)}


def get_present_players(trial_id):
    """Returns only the players marked present, sorted by trial number."""
    # A set of ids gives an instant 'is this player present?' check
    present_ids = {a["player_id"] for a in _read_attendance(trial_id) if a["is_present"] == 1}
    players = [p for p in _read_players(trial_id) if p["player_id"] in present_ids]
    return sorted(players, key=lambda p: p["trial_number"])


# --------------------------------------------------------------------------- #
# Rounds & Assignments
# --------------------------------------------------------------------------- #

def _read_rounds(trial_id):
    """Reads the Rounds file for one trial (one row per team per round)."""
    trial = get_trial(trial_id)
    # An unknown trial id has no file to read
    if not trial:
        return []
    return _read_table(
        _trial_file(trial, "Rounds"),
        int_fields=["round_id", "trial_id", "round_number", "court_number"],
    )


def _write_rounds(trial_id, rows):
    """Writes the Rounds file for one trial."""
    trial = get_trial(trial_id)
    # Only write if the trial exists (the file path is built from the trial)
    if trial:
        _write_table(_trial_file(trial, "Rounds"), ROUNDS_FIELDS, rows)


def _read_assignments(trial_id):
    """Reads the Assignments file for one trial (who plays which position in which round)."""
    trial = get_trial(trial_id)
    # An unknown trial id has no file to read
    if not trial:
        return []
    return _read_table(
        _trial_file(trial, "Assignments"),
        int_fields=["assignment_id", "round_id", "player_id"],
    )


def _write_assignments(trial_id, rows):
    """Writes the Assignments file for one trial."""
    trial = get_trial(trial_id)
    # Only write if the trial exists (the file path is built from the trial)
    if trial:
        _write_table(_trial_file(trial, "Assignments"), ASSIGNMENTS_FIELDS, rows)


def clear_rounds_for_trial(trial_id):
    """Removes the whole draw (rounds and assignments) for a trial."""
    _write_rounds(trial_id, [])
    _write_assignments(trial_id, [])


def create_round_entry(trial_id, round_number, court_number, team, bib_colour):
    """Adds one team's row for one round and returns its round_id."""
    rounds = _read_rounds(trial_id)
    round_id = _next_id(rounds, "round_id")
    rounds.append({
        "round_id": round_id,
        "trial_id": trial_id,
        "round_number": round_number,
        "court_number": court_number,
        "team": team,
        "bib_colour": bib_colour,
    })
    _write_rounds(trial_id, rounds)
    return round_id


def create_assignment(trial_id, round_id, player_id, position):
    """Adds one player-in-a-position row to a round."""
    assignments = _read_assignments(trial_id)
    assignments.append({
        "assignment_id": _next_id(assignments, "assignment_id"),
        "round_id": round_id,
        "player_id": player_id,
        "position": position,
    })
    _write_assignments(trial_id, assignments)


def get_rounds_for_trial(trial_id):
    """Returns a trial's rounds sorted by round, court and team."""
    rounds = _read_rounds(trial_id)
    return sorted(rounds, key=lambda r: (r["round_number"], r["court_number"], r["team"]))


def get_assignments_for_round(trial_id, round_id):
    """Returns the assignments for one round, each with the player's name and trial number added."""
    # Lookup of {player_id: player} so names can be added to each assignment without searching
    players_by_id = {p["player_id"]: p for p in _read_players(trial_id)}
    rows = []
    # Keep only this round's assignments and add the player's name and number to each
    for a in _read_assignments(trial_id):
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
    """Reads every login account from users.csv."""
    return _read_table(USERS_CSV, int_fields=["user_id"])


def create_user(username, password_hash, role, salt=""):
    """Adds a login account. The password must already be hashed (never stored as typed)."""
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
    """Returns the account with this username as a dict, or None."""
    return next((u for u in _read_users() if u["username"] == username), None)


# --------------------------------------------------------------------------- #
# CSV export - clean player register, for the Export tab
# --------------------------------------------------------------------------- #

# Column titles written at the top of the exported CSV. A list, because the order is the
# column order; heading 1 goes with field 1 of PLAYER_FIELD_ORDER, and so on.
CSV_HEADERS = ["Trial No", "First Name", "Last Name", "DOB", "Position 1", "Position 2"]

# Which player fields go in each column, in the same order as CSV_HEADERS. Two matching lists,
# so the readable headings can differ from the stored field names but stay in column order.
PLAYER_FIELD_ORDER = ["trial_number", "first_name", "last_name", "dob", "position_1", "position_2"]


def export_players_csv(players, filepath):
    """Writes the given players to a clean CSV (header row + one row per player) and returns the path."""
    directory = os.path.dirname(filepath)
    # Make the folder if the path has one (a bare file name has no folder)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        # One row per player, with the fields in the same order as the headings
        for p in players:
            row = [p.get(field, "") for field in PLAYER_FIELD_ORDER]
            writer.writerow(row)

    return filepath


# Folder where each trial's up-to-date player CSV is kept
EXPORTS_DIR = "exports"


def export_trial_csv(trial_id):
    """Writes/updates exports/<trial name>_players.csv for this trial.
    Called automatically whenever a trial is created or a player is added,
    so there's always an up-to-date CSV on disk without needing to press
    the Export tab's button."""
    trial = get_trial(trial_id)
    # Unknown trial id: nothing to export
    if not trial:
        return None
    safe_name = trial["trial_name"].replace(" ", "_") or f"trial_{trial_id}"
    filepath = os.path.join(EXPORTS_DIR, f"{safe_name}_players.csv")
    return export_players_csv(get_players_for_trial(trial_id), filepath)


# --------------------------------------------------------------------------- #
# Draw exports: game sheets (PDF) and player reference sheet (CSV)
# --------------------------------------------------------------------------- #

def get_draw(trial_id):
    """Returns the whole draw as a list of teams in round/court/team order.
    Each team is a dict: round_number, court_number, team, bib_colour and
    players (each player's fields plus 'position', in court order GS..GK)."""
    # Lookup of {player_id: player} so each assignment can show the player's details
    players_by_id = {p["player_id"]: p for p in _read_players(trial_id)}
    # Assignments grouped by round_id, so each team's line-up is found without re-reading the file
    by_round = {}
    for a in _read_assignments(trial_id):
        by_round.setdefault(a["round_id"], []).append(a)

    draw = []
    # For each team in the draw, build its line-up and sort it into court order GS to GK
    for r in get_rounds_for_trial(trial_id):
        lineup = []
        # Copy each player's details and add the position they play in this round
        for a in by_round.get(r["round_id"], []):
            player = dict(players_by_id.get(a["player_id"], {}))
            player["position"] = a["position"]
            lineup.append(player)
        lineup.sort(key=lambda p: POSITIONS.index(p["position"]) if p["position"] in POSITIONS else 99)
        draw.append({
            "round_number": r["round_number"], "court_number": r["court_number"],
            "team": r["team"], "bib_colour": r["bib_colour"], "players": lineup,
        })
    return draw


def _player_name(p):
    """Returns 'First Last' for a player dict."""
    return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()


def export_game_sheets_pdf(trial_id, filepath):
    """Writes a PDF with one page per court per round. Each page has the two
    teams side by side, with a Position / Name / Rating table and a
    Notes/Feedback box under every player, ready to print for the selectors.
    Needs the reportlab package. Returns the file path."""
    # Imported here so the rest of the program still runs if reportlab is missing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak, Spacer
    from xml.sax.saxutils import escape

    trial = get_trial(trial_id)
    draw = get_draw(trial_id)
    # Nothing to print without a trial and a saved draw
    if not trial or not draw:
        raise ValueError("This trial has no draw yet.")

    normal = ParagraphStyle("n", fontName="Helvetica", fontSize=9, leading=11, alignment=1)
    title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=18, leading=22)
    sub = ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=10, leading=14)
    right = ParagraphStyle("r", fontName="Helvetica", fontSize=10, leading=14)

    # Wording for the born-in line, e.g. "(born in 2013 & 2014)"
    years = [str(y) for y in (trial.get("min_birth_year"), trial.get("max_birth_year")) if y]
    born = f" (born in {' & '.join(dict.fromkeys(years))})" if years else ""

    def team_table(team):
        """Builds one team's table: title bar, header row, then a player row and notes row per position."""
        # toColor raises ValueError for a colour name reportlab does not know
        try:
            bg = colors.toColor(team["bib_colour"])
        except ValueError:
            bg = colors.lightgrey  # unknown colour name: plain grey title bar
        # White text on dark bibs, black text on light bibs
        fg = colors.white if (0.299 * bg.red + 0.587 * bg.green + 0.114 * bg.blue) < 0.55 else colors.black
        rows = [[f"Team {team['team']} - {team['bib_colour']}", "", ""], ["Position", "Name", "Rating"]]
        heights = [22, 20]
        style = [
            ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), fg),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]
        # Two rows per player: position, name and rating, then a Notes/Feedback row across the full width
        for p in team["players"]:
            name = escape(_player_name(p)) + f" - ({p.get('trial_number', '')})"
            prefs = f"({p.get('position_1', '')} | {p.get('position_2', '')})"
            rows.append([p["position"], Paragraph(f"{name}<br/>{escape(prefs)}", normal), ""])
            rows.append(["Notes/Feedback:", "", ""])
            heights += [30, 52]
            notes_row = len(rows) - 1
            style += [("SPAN", (0, notes_row), (-1, notes_row)),
                      ("ALIGN", (0, notes_row), (0, notes_row), "LEFT"),
                      ("VALIGN", (0, notes_row), (0, notes_row), "TOP")]
        table = Table(rows, colWidths=[52, 128, 44], rowHeights=heights)
        table.setStyle(TableStyle(style))
        return table

    # Group the teams by (round, court) so each pair shares a page
    pages = {}
    for team in draw:
        pages.setdefault((team["round_number"], team["court_number"]), {})[team["team"]] = team

    story = []
    # One page for each court in each round, in round then court order
    for page_number, ((round_number, court_number), teams) in enumerate(sorted(pages.items())):
        # Every page after the first starts with a page break
        if page_number:
            story.append(PageBreak())
        header = Table([[
            [Paragraph(escape(trial["trial_name"]), title), Paragraph("Selection Sheet", sub)],
            [Paragraph(f"<b>SELECTIONS:</b> {escape(trial['trial_name'])}{born}", right),
             Paragraph(f"<b>DATE:</b> {escape(str(trial['trial_date']))}", right),
             Paragraph(f"<b>Match Details:</b> Round {round_number} - Court {court_number}", right)],
        ]], colWidths=[210, 290])
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [header, Spacer(1, 10)]
        both = Table([[team_table(teams[t]) if t in teams else "" for t in ("A", "B")]], colWidths=[250, 250])
        both.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(both)

    directory = os.path.dirname(filepath)
    # Make the folder if the path has one (a bare file name has no folder)
    if directory:
        os.makedirs(directory, exist_ok=True)
    SimpleDocTemplate(filepath, pagesize=A4, leftMargin=40, rightMargin=40,
                      topMargin=36, bottomMargin=30, title="Selection Sheets").build(story)
    return filepath


def export_reference_sheet_csv(trial_id, filepath):
    """Writes a CSV (opens in Excel) with one row per player and one column per round,
    each cell saying which court, position and bib colour that player has, so a player
    can find their own row and read across. A '-' means they are resting. Returns the file path."""
    trial = get_trial(trial_id)
    draw = get_draw(trial_id)
    # Nothing to write without a trial and a saved draw
    if not trial or not draw:
        raise ValueError("This trial has no draw yet.")

    round_numbers = sorted({t["round_number"] for t in draw})
    # cells[player_id][round_number] = "Court 2: GS (Blue)"; players holds each player's details
    cells, players = {}, {}
    # Fill in one cell for every player in every team of the draw
    for team in draw:
        for p in team["players"]:
            players[p["player_id"]] = p
            cells.setdefault(p["player_id"], {})[team["round_number"]] = (
                f"Court {team['court_number']}: {p['position']} ({team['bib_colour']})")

    directory = os.path.dirname(filepath)
    # Make the folder if the path has one (a bare file name has no folder)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel reads it correctly
        writer = csv.writer(f)
        writer.writerow(["Player", "Number", "Positions"] + [f"Round {n}" for n in round_numbers])
        # One row per player in trial-number order; a round with no cell shows '-'
        for pid in sorted(players, key=lambda i: players[i].get("trial_number") or 0):
            p = players[pid]
            prefs = " ".join(x for x in (p.get("position_1"), p.get("position_2")) if x)
            writer.writerow([_player_name(p), p.get("trial_number", ""), prefs]
                            + [cells[pid].get(n, "-") for n in round_numbers])
    return filepath


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

# A list of names for the raw export's columns, in file order. It is a written record only:
# parse_raw_rows() reads each column by its number (row[11]), because the club's export may
# or may not have a header row to read names from.
RAW_COLUMNS = [
    "trial_no", "full_name", "dob", "netball_id", "address", "phone", "email",
    "parent_name", "parent_phone", "parent_email", "playing_history",
    "position_1", "position_2", "position_3",
]

def find_csv_files():
    """Returns every .csv file in the same folder as this script, in name order."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return sorted(glob.glob(os.path.join(script_dir, "*.csv")))


def _read_rows(filepath):
    """Reads a CSV file as lists of cells, skipping completely blank rows."""
    with open(filepath, newline="", encoding="utf-8") as f:
        return [row for row in csv.reader(f) if row and any(cell.strip() for cell in row)]


def detect_format(rows):
    """Returns 'clean' if the first row is this program's own header, otherwise 'raw' (a registration export)."""
    # An empty file has no header to check
    if not rows:
        return "raw"
    first_row = [cell.strip() for cell in rows[0]]
    # Compare the first six cells with this program's own headings
    if first_row[:len(CSV_HEADERS)] == CSV_HEADERS:
        return "clean"
    return "raw"


def split_full_name(full_name):
    """Splits 'First Last' at the first space into (first, last). One word gives (word, '')."""
    full_name = full_name.strip()
    # A single word has no last name
    if " " not in full_name:
        return full_name, ""
    first, last = full_name.split(" ", 1)
    return first, last


def parse_clean_rows(rows):
    """Turns rows in this program's own export format into player dicts (skips the header)."""
    players = []
    # Skip the header (row 0); a row with fewer than 6 cells can't hold a player
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
    """Turns rows from a registration export into player dicts. Skips a header row if the third
    column is not a date, and any row with fewer than 13 columns."""
    start_index = 0
    # If the third cell of the first row is not a date, the first row is a header: start at row 1
    if rows and len(rows[0]) > 2 and not is_valid_date(rows[0][2].strip()):
        start_index = 1

    players = []
    # One player per row; a row with fewer than 13 cells is incomplete and skipped
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


# Reads the club's registration export, so 100+ players don't have to be typed in by hand.
# It works out which layout the file is, then hands back plain dictionaries either way.
def load_csv(filepath):
    """Reads a CSV file and returns (list of player dicts, 'clean' or 'raw')."""
    rows = _read_rows(filepath)
    fmt = detect_format(rows)
    # Each layout has its own parser
    if fmt == "clean":
        return parse_clean_rows(rows), fmt
    return parse_raw_rows(rows), fmt


def trial_name_from_filename(filepath):
    """Uses the file name without .csv as the trial name, e.g. U17_2026_players."""
    return os.path.splitext(os.path.basename(filepath))[0]


def get_or_create_trial(trial_name, age_group, trial_date, num_courts):
    """Returns (trial_id, created). Reuses a trial with the same name, otherwise makes a new one."""
    existing = next((t for t in get_all_trials() if t["trial_name"] == trial_name), None)
    # Reuse the trial if one with this name already exists
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
    # Keep asking until the answer is a real position, or blank to skip the player
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
    """Loads one CSV file into its own trial (named after the file) and returns
    (players loaded, rows skipped). Skips rows with no name or a bad date, players
    already in the trial (same netball ID, or same name and DOB), and players whose
    positions the coordinator does not correct when asked."""
    # One export file becomes one trial, named after the file. Each row is checked on its own
    # (name, date, positions, duplicates) so one bad row is skipped instead of the whole file.
    trial_name = trial_name_from_filename(filepath)
    age_group = trial_name

    # A file that can't be opened or read is reported and skipped, so the other files still load
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
    # A set, not a list: the only question is "have we seen this ID?", and a set answers that
    # quickly and holds no repeats. Blank IDs are left out so two blanks don't count as a match.
    seen_netball_ids = {p["netball_id"] for p in existing if p["netball_id"]}
    # A set of (first, last, dob) tuples. A tuple can go in a set (a list can't) and all three
    # parts must match. Names are lower-cased so "Emma" and "emma" are the same person.
    seen_name_dobs = {
        (p["first_name"].strip().lower(), p["last_name"].strip().lower(), p["dob"])
        for p in existing
    }

    # Counters for the summary line printed when this file is done. Four separate whole numbers,
    # not one total, because the summary reports each kind of skipped row separately.
    loaded = 0
    skipped = 0
    duplicates = 0
    bad_positions = 0
    # Check each row in turn; continue moves on to the next row without saving this one
    for p in players:
        # Existence check: a player needs a first and a last name
        if not p["first_name"] or not p["last_name"]:
            skipped += 1
            continue
        # Type check: the date of birth must be a real DD/MM/YYYY date
        if not is_valid_date(p["dob"]):
            skipped += 1
            continue

        position_1 = p["position_1"]
        position_2 = p["position_2"]
        player_label = f"{p['first_name']} {p['last_name']} (DOB {p['dob']})"
        # A position that is not one of the seven is put to the coordinator to correct
        if position_1 not in POSITIONS:
            position_1 = _prompt_for_position("Position 1", position_1, player_label)
        # Position 2 is only asked about if Position 1 was not skipped
        if position_1 is not None and position_2 not in POSITIONS:
            position_2 = _prompt_for_position("Position 2", position_2, player_label)
        # None means the coordinator chose to skip this player
        if position_1 is None or position_2 is None:
            bad_positions += 1
            continue

        netball_id = p.get("netball_id", "")
        name_dob = (p["first_name"].strip().lower(), p["last_name"].strip().lower(), p["dob"])
        # Already in the trial: same Netball ID (if it has one), or same name and date of birth
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
        # Remember this player so a repeat later in the same file is also skipped
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
    """Asks in the terminal for the trial date and number of courts if they were not given as options."""
    # Only ask for what was not given as a command-line option
    if not args.date:
        args.date = input("Trial date for all trials (DD/MM/YYYY): ").strip()
    if not args.courts:
        courts_input = input("Number of courts for all trials [1]: ").strip()
        args.courts = int(courts_input) if courts_input else 1
    return args


def main():
    """Loads every CSV in this folder into its own trial and prints a summary."""
    parser = argparse.ArgumentParser(
        description="Scans this script's folder for CSV files and loads each one into its "
                     "own trial (named after the file)."
    )
    # The export has no trial date or court count in it, so they are given once here (or asked
    # for) and applied to every file that gets loaded.
    parser.add_argument("--date", default=None, help="Trial date applied to every CSV, DD/MM/YYYY")
    parser.add_argument("--courts", type=int, default=None,
                         help="Number of courts applied to every CSV (defaults to 1)")
    args = parser.parse_args()

    csv_files = find_csv_files()
    # No CSV files next to the script: say so and stop
    if not csv_files:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"No CSV files found in {script_dir} - nothing to load.")
        return

    print(f"Found {len(csv_files)} CSV file(s): {', '.join(os.path.basename(f) for f in csv_files)}")
    args = prompt_for_shared_settings(args)

    init_data()

    total_loaded = 0
    total_skipped = 0
    # Load each file into its own trial and add up the totals
    for filepath in csv_files:
        loaded, skipped = seed_from_csv(filepath, args.date, args.courts)
        total_loaded += loaded
        total_skipped += skipped

    print(f"\nDone - {total_loaded} player(s) loaded across {len(csv_files)} file(s), "
          f"{total_skipped} row(s) skipped.")


# --------------------------------------------------------------------------- #
# Test data generation
# --------------------------------------------------------------------------- #

# Name lists used to make random test players
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
    """Returns a random DD/MM/YYYY date of birth in 2013 or 2014 (day 1 to 28 so it is always a real date)."""
    year = random.choice([2013, 2014])
    day = random.randint(1, 28)
    month = random.randint(1, 12)
    return f"{day:02d}/{month:02d}/{year}"


def _random_positions():
    """Returns two different random positions (1st and 2nd preference)."""
    pos1 = random.choice(POSITIONS)
    pos2 = random.choice([p for p in POSITIONS if p != pos1])
    return pos1, pos2


def generate_test_players(count=100):
    """Returns `count` made-up players as (first, last, dob, position 1, position 2) tuples."""
    # Fixed seed, so the same made-up players are produced every time (repeatable tests)
    random.seed(42)
    players = []
    # Build one made-up player per pass; _ is used because the counter itself is not needed
    for _ in range(count):
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        dob = _random_dob()
        pos1, pos2 = _random_positions()
        players.append((first_name, last_name, dob, pos1, pos2))
    return players


def load_test_players(count=100):
    """Creates 'Test Trial (count)' if needed and adds the made-up players to it."""
    trial_name = f"Test Trial ({count})"
    trials = get_all_trials()
    existing = next((t for t in trials if t["trial_name"] == trial_name), None)

    # Reuse the test trial if it already exists, otherwise create it
    if existing:
        trial_id = existing["trial_id"]
        print(f"Using existing trial: {trial_name} (id {trial_id})")
    else:
        create_trial(trial_name, "U13", "01/09/2026")
        trial_id = next(t["trial_id"] for t in get_all_trials() if t["trial_name"] == trial_name)
        print(f"Created new trial '{trial_name}' (id {trial_id})")

    players = generate_test_players(count)
    # Save each made-up player and print the trial number they were given
    for first_name, last_name, dob, pos1, pos2 in players:
        trial_number = create_player(trial_id, first_name, last_name, dob, pos1, pos2)
        print(f"  #{trial_number} {first_name} {last_name} ({pos1}/{pos2})")

    print(f"\nDone - {len(players)} test players added to trial id {trial_id}.")


if __name__ == "__main__":
    main()
