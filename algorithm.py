"""
Works out the netball position rotation for a trial.

Each round is built in three passes over all the slots at once:
  1. Give each position to whoever still needs it as their 1st choice.
  2. Give whatever's left to whoever still needs their 2nd choice.
  3. Fill anything still empty with whoever has sat out longest.

generate_minimum_rounds() keeps adding rounds until everyone has played
both their preferred positions at least once.
"""

import math
import random

POSITION_ORDER = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]
PLAYERS_PER_TEAM = 7
MAX_ROUNDS = 80

BIB_COLOUR_POOL = [
    ("Black", "Pink"),
    ("Blue", "Orange"),
    ("Red", "White"),
    ("Green", "Yellow"),
]


def bib_colours_for_court(court_number):
    pair = BIB_COLOUR_POOL[(court_number - 1) % len(BIB_COLOUR_POOL)]
    return {"A": pair[0], "B": pair[1]}


COURT_BIB_COLOURS = {c: bib_colours_for_court(c) for c in range(1, 5)}


def theoretical_minimum_rounds(players, num_courts):
    """Lower bound on rounds needed, from slot supply vs preference demand."""
    if not players:
        return 0
    demand = {}
    for p in players:
        demand[p["position_1"]] = demand.get(p["position_1"], 0) + 1
        if p["position_2"] != p["position_1"]:
            demand[p["position_2"]] = demand.get(p["position_2"], 0) + 1
    slots_per_position = 2 * num_courts
    lb_position = max(math.ceil(d / slots_per_position) for d in demand.values())
    needs = sum(1 if p["position_1"] == p["position_2"] else 2 for p in players)
    lb_slots = math.ceil(needs / (PLAYERS_PER_TEAM * 2 * num_courts))
    return max(lb_position, lb_slots)


def _build_slots(num_courts):
    return [
        {"court_number": c, "team": t, "position": pos}
        for c in range(1, num_courts + 1)
        for t in ("A", "B")
        for pos in POSITION_ORDER
    ]


def _claim(slots_for_pos, ranked, used, filled, skip):
    free = [s for s in slots_for_pos if s not in filled]
    winners = ranked[: len(free)]
    for slot, player in zip(free, winners):
        filled[slot] = player
        used.add(player["player_id"])
    for player in ranked[len(free):]:
        skip[player["player_id"]] += 1
    return winners


def generate_rounds(players, num_rounds, num_courts=1):
    """Generate `num_rounds` rounds across `num_courts` courts."""
    if num_courts < 1:
        raise ValueError("num_courts must be at least 1.")
    if num_rounds < 1:
        raise ValueError("num_rounds must be at least 1.")

    players_needed = PLAYERS_PER_TEAM * 2 * num_courts
    if len(players) < players_needed:
        raise ValueError(
            f"Need at least {players_needed} present players for {num_courts} court(s), "
            f"got {len(players)}."
        )

    ids = [p["player_id"] for p in players]
    pos1_done = {pid: False for pid in ids}
    pos2_done = {pid: False for pid in ids}
    skip1 = {pid: 0 for pid in ids}
    skip2 = {pid: 0 for pid in ids}
    bench_wait = {pid: 0 for pid in ids}

    slot_template = _build_slots(num_courts)
    slots_by_position = {
        pos: [i for i, s in enumerate(slot_template) if s["position"] == pos]
        for pos in POSITION_ORDER
    }

    rounds_output = []

    for round_number in range(1, num_rounds + 1):
        filled = {}
        used = set()

        for pos in POSITION_ORDER:
            ranked = sorted(
                (p for p in players
                 if p["position_1"] == pos
                 and not pos1_done[p["player_id"]]
                 and p["player_id"] not in used),
                key=lambda p: (-skip1[p["player_id"]], -bench_wait[p["player_id"]], p["player_id"]),
            )
            _claim(slots_by_position[pos], ranked, used, filled, skip1)

        for pos in POSITION_ORDER:
            ranked = sorted(
                (p for p in players
                 if p["position_2"] == pos
                 and not pos2_done[p["player_id"]]
                 and p["player_id"] not in used),
                key=lambda p: (-skip2[p["player_id"]], -bench_wait[p["player_id"]], p["player_id"]),
            )
            _claim(slots_by_position[pos], ranked, used, filled, skip2)

        spare = sorted(
            (p for p in players if p["player_id"] not in used),
            key=lambda p: (-bench_wait[p["player_id"]], p["player_id"]),
        )
        spare_iter = iter(spare)
        for index in range(len(slot_template)):
            if index in filled:
                continue
            player = next(spare_iter)
            filled[index] = player
            used.add(player["player_id"])

        by_team = {}
        for index, slot in enumerate(slot_template):
            player = filled[index]
            pid = player["player_id"]
            key = (slot["court_number"], slot["team"])
            by_team.setdefault(key, []).append(
                {"position": slot["position"], "player_id": pid}
            )
            if slot["position"] == player["position_1"] and not pos1_done[pid]:
                pos1_done[pid] = True
            if slot["position"] == player["position_2"] and not pos2_done[pid]:
                pos2_done[pid] = True

        for (court_number, team), assignments in sorted(by_team.items()):
            rounds_output.append({
                "round_number": round_number,
                "court_number": court_number,
                "team": team,
                "assignments": assignments,
            })

        for pid in ids:
            bench_wait[pid] = 0 if pid in used else bench_wait[pid] + 1

    return rounds_output


def check_guarantee_met(players, rounds_output):
    """Returns player ids who haven't yet played both preferred positions."""
    by_id = {p["player_id"]: p for p in players}
    seen1, seen2 = set(), set()
    for round_data in rounds_output:
        for a in round_data["assignments"]:
            player = by_id.get(a["player_id"])
            if player is None:
                continue
            if a["position"] == player["position_1"]:
                seen1.add(player["player_id"])
            if a["position"] == player["position_2"]:
                seen2.add(player["player_id"])
    return [p["player_id"] for p in players
            if p["player_id"] not in seen1 or p["player_id"] not in seen2]


def generate_minimum_rounds(players, num_courts=1, max_rounds=MAX_ROUNDS):
    """Keeps adding rounds until every player has had both positions."""
    for num_rounds in range(1, max_rounds + 1):
        rounds_output = generate_rounds(players, num_rounds, num_courts)
        failed = check_guarantee_met(players, rounds_output)
        if not failed:
            return rounds_output, num_rounds, []
    return rounds_output, max_rounds, failed


# --------------------------------------------------------------------------- #
# Stress test - run with `python algorithm.py` to check a wide spread of
# roster sizes/court counts still gets a fair draw.
# --------------------------------------------------------------------------- #

def _random_roster(seed, n, demand_skew=0.0, skewed_position="GK"):
    random.seed(seed)
    players = []
    for i in range(n):
        if demand_skew and random.random() < demand_skew:
            pos1 = skewed_position
        else:
            pos1 = random.choice(POSITION_ORDER)
        pos2 = random.choice([p for p in POSITION_ORDER if p != pos1])
        players.append({"player_id": i + 1, "position_1": pos1, "position_2": pos2})
    return players


def _build_sweep_configs():
    configs = []
    seed = 0
    for num_courts in (1, 2, 3):
        min_needed = 14 * num_courts
        for n in (14, 28, 50, 100, 150):
            if n < min_needed:
                continue
            for skew in (0.0, 0.3, 0.7):
                configs.append((seed, n, num_courts, skew))
                seed += 1
    return configs


def run_stress_test(quick=False):
    if quick:
        configs = [(seed, 100, 2, 0.0) for seed in range(50)]
    else:
        configs = _build_sweep_configs()

    failures = 0
    optimal = 0
    max_rounds_seen = 0
    total_rounds = 0

    for seed, n, num_courts, skew in configs:
        roster = _random_roster(seed, n, demand_skew=skew)
        rounds_output, rounds_used, failed = generate_minimum_rounds(roster, num_courts)
        lower_bound = theoretical_minimum_rounds(roster, num_courts)

        max_rounds_seen = max(max_rounds_seen, rounds_used)
        total_rounds += rounds_used
        if rounds_used == lower_bound:
            optimal += 1

        if failed:
            failures += 1
            print(f"n={n:>3} courts={num_courts} skew={skew}: FAILED - "
                  f"{len(failed)} player(s) still missing a preference after {rounds_used} rounds")

    print()
    print(f"{len(configs) - failures}/{len(configs)} rosters fully satisfied the guarantee")
    print(f"{optimal}/{len(configs)} draws used the theoretical minimum number of rounds")
    print(f"Max rounds needed across all rosters: {max_rounds_seen}")
    print(f"Average rounds needed: {total_rounds / len(configs):.1f}")


if __name__ == "__main__":
    import sys
    run_stress_test(quick=(len(sys.argv) > 1 and sys.argv[1] == "quick"))
