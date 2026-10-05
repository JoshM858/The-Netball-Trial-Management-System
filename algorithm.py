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

# Standard court order, goal shooter (GS) to goal keeper (GK); slots are also filled in this
# order. A list, not a set, because order matters: every team's slots line up the same way.
# Text, because positions are codes, not numbers.
POSITION_ORDER = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]
# A netball team has 7 players on court. Named once so the rule isn't repeated as a bare 7 or
# 14 in several places; capitals because it never changes while the program runs.
PLAYERS_PER_TEAM = 7
# Safety cap so the program cannot loop forever if a roster can never be satisfied. It is not a
# target: the loop normally stops as soon as everyone has had both positions.
MAX_ROUNDS = 80

# Set True to print how many slots each phase fills in every round (debugging). A True/False
# switch, because it is only ever on or off. It is a global so generate_rounds() can check it
# in two places. False by default, so a normal run prints nothing.
DEBUG = False

# (Team A colour, Team B colour) for each court; repeats after four courts. Each pair is a
# tuple because the two colours always go together and never change. The list is indexed by
# court number (see bib_colours_for_court).
BIB_COLOUR_POOL = [
    ("Black", "Pink"),
    ("Blue", "Orange"),
    ("Red", "White"),
    ("Green", "Yellow"),
]


def bib_colours_for_court(court_number):
    """Returns {"A": colour, "B": colour} for a court, repeating the pool after four courts."""
    pair = BIB_COLOUR_POOL[(court_number - 1) % len(BIB_COLOUR_POOL)]
    return {"A": pair[0], "B": pair[1]}


# A dictionary keyed by court number, so one court's colours are looked up directly, e.g.
# COURT_BIB_COLOURS[2]["A"], not searched for. Built once for courts 1 to 4.
COURT_BIB_COLOURS = {c: bib_colours_for_court(c) for c in range(1, 5)}


def theoretical_minimum_rounds(players, num_courts):
    """Lower bound on rounds needed, from slot supply vs preference demand."""
    # No players means no rounds are needed
    if not players:
        return 0
    # demand[position] = how many players want that position as 1st or 2nd choice. A dictionary,
    # because the positions are the keys and .get(position, 0) starts a count at 0 the first time.
    demand = {}
    # Count each player's 1st choice, and their 2nd if it is a different position
    for p in players:
        demand[p["position_1"]] = demand.get(p["position_1"], 0) + 1
        if p["position_2"] != p["position_1"]:
            demand[p["position_2"]] = demand.get(p["position_2"], 0) + 1
    # Each court has two teams, so 2 slots per position per court
    slots_per_position = 2 * num_courts
    lb_position = max(math.ceil(d / slots_per_position) for d in demand.values())
    needs = sum(1 if p["position_1"] == p["position_2"] else 2 for p in players)
    lb_slots = math.ceil(needs / (PLAYERS_PER_TEAM * 2 * num_courts))
    return max(lb_position, lb_slots)


def _build_slots(num_courts):
    """Returns every place on court for one round: (court, team, position) for each court, both teams, all 7 positions."""
    return [
        {"court_number": c, "team": t, "position": pos}
        for c in range(1, num_courts + 1)
        for t in ("A", "B")
        for pos in POSITION_ORDER
    ]


def _claim(slots_for_pos, ranked, used, filled, skip):
    """Gives the free slots of one position to the top-ranked players and returns those winners.
    Players who were ranked but missed out get 1 added to their skip counter, so they rank higher next round."""
    free = [s for s in slots_for_pos if s not in filled]
    winners = ranked[: len(free)]
    # Pair each free slot with the next winner; zip stops when either list runs out
    for slot, player in zip(free, winners):
        filled[slot] = player
        used.add(player["player_id"])
    # Ranked players beyond the free slots missed out this round
    for player in ranked[len(free):]:
        skip[player["player_id"]] += 1
    return winners


def generate_rounds(players, num_rounds, num_courts=1):
    """Generate `num_rounds` rounds across `num_courts` courts."""
    # Range checks: there must be at least one court and one round
    if num_courts < 1:
        raise ValueError("num_courts must be at least 1.")
    if num_rounds < 1:
        raise ValueError("num_rounds must be at least 1.")

    # A position that is not one of the seven can never be given out, so refuse it now
    # instead of looping until MAX_ROUNDS.
    for p in players:
        if p["position_1"] not in POSITION_ORDER or p["position_2"] not in POSITION_ORDER:
            raise ValueError(f"Player {p['player_id']} has a position that is not one of {', '.join(POSITION_ORDER)}.")

    players_needed = PLAYERS_PER_TEAM * 2 * num_courts
    # Existence check: two full teams of 7 are needed for every court
    if len(players) < players_needed:
        raise ValueError(
            f"Need at least {players_needed} present players for {num_courts} court(s), "
            f"got {len(players)}."
        )

    # The dicts below each track every player through the trial
    # A list of every player id, made once so all the dictionaries below use the same keys.
    ids = [p["player_id"] for p in players]
    # pos1_done / pos2_done: has the player played their 1st / 2nd preference yet? Dictionaries of
    # player id -> True/False, because that is the only question. One each, so the two are tracked
    # separately.
    pos1_done = {pid: False for pid in ids}
    pos2_done = {pid: False for pid in ids}
    # skip1 / skip2: times a player needed a preferred slot but missed out (more misses = higher in
    # the queue). Whole-number counters, not True/False, so someone who missed out twice is ranked
    # ahead of someone who missed out once (see the sort keys below).
    skip1 = {pid: 0 for pid in ids}
    skip2 = {pid: 0 for pid in ids}
    # Rounds in a row the player has sat out; used to choose filler players fairly. A counter, set
    # back to 0 when they play, so whoever has waited longest is picked first.
    bench_wait = {pid: 0 for pid in ids}

    # One entry for every place on court in a round (court, team, position). A list, because each
    # slot is referred to by its number (its index). Built once and reused every round.
    slot_template = _build_slots(num_courts)
    # {position: [slot numbers]} so each position's slots can be found quickly. It holds slot
    # numbers, not copies of the slots, so there is only ever one copy of each slot.
    slots_by_position = {
        pos: [i for i, s in enumerate(slot_template) if s["position"] == pos]
        for pos in POSITION_ORDER
    }

    rounds_output = []

    # Build one round at a time; the counters above carry over from round to round
    for round_number in range(1, num_rounds + 1):
        # filled: slot number -> the player placed there this round. A dictionary, because slots are
        # filled out of order (all the GS first, then GA...) and `index in filled` says if one is taken.
        filled = {}
        # used: ids already placed this round. A set, because a player can only be placed once and the
        # only question is 'already in?' (a quick check, and adding the same id twice does nothing).
        used = set()

        # Phase A: give each position's slots to players who still need it as their 1st choice
        for pos in POSITION_ORDER:
            ranked = sorted(
                (p for p in players
                 if p["position_1"] == pos
                 and not pos1_done[p["player_id"]]
                 and p["player_id"] not in used),
                key=lambda p: (-skip1[p["player_id"]], -bench_wait[p["player_id"]], p["player_id"]),
            )
            _claim(slots_by_position[pos], ranked, used, filled, skip1)

        filled_by_a = len(filled)

        # Phase B: same again for 2nd choices, using the slots Phase A left free
        for pos in POSITION_ORDER:
            ranked = sorted(
                (p for p in players
                 if p["position_2"] == pos
                 and not pos2_done[p["player_id"]]
                 and p["player_id"] not in used),
                key=lambda p: (-skip2[p["player_id"]], -bench_wait[p["player_id"]], p["player_id"]),
            )
            _claim(slots_by_position[pos], ranked, used, filled, skip2)

        filled_by_b = len(filled) - filled_by_a

        # Phase C: everyone not yet placed, longest on the bench first, fills the slots still empty
        spare = sorted(
            (p for p in players if p["player_id"] not in used),
            key=lambda p: (-bench_wait[p["player_id"]], p["player_id"]),
        )
        spare_iter = iter(spare)
        # Walk every slot in order; a slot already filled in phase A or B is skipped
        for index in range(len(slot_template)):
            if index in filled:
                continue
            player = next(spare_iter)
            filled[index] = player
            used.add(player["player_id"])

        if DEBUG:
            # Slots filled by each phase this round (C is whatever A and B left)
            print(f"Round {round_number}: phase A filled {filled_by_a} slots, phase B {filled_by_b}, "
                  f"phase C {len(slot_template) - filled_by_a - filled_by_b}")

        # by_team: (court, team) -> list of {position, player} used to build the output. The key is a
        # tuple, because a tuple can be a dictionary key and a list can't.
        by_team = {}
        # Put each placed player into their team's list, and tick off a preference if this slot is one
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

        # One output row per team, sorted by court then team
        for (court_number, team), assignments in sorted(by_team.items()):
            rounds_output.append({
                "round_number": round_number,
                "court_number": court_number,
                "team": team,
                "assignments": assignments,
            })

        for pid in ids:
            # Players who played reset to 0; everyone else has sat out one more round
            bench_wait[pid] = 0 if pid in used else bench_wait[pid] + 1

        if DEBUG:
            # Players who have not yet played both of their preferred positions
            waiting = sum(1 for pid in ids if not (pos1_done[pid] and pos2_done[pid]))
            print(f"    {waiting} player(s) still need a preferred position")

    return rounds_output


def check_guarantee_met(players, rounds_output):
    """Returns player ids who haven't yet played both preferred positions."""
    by_id = {p["player_id"]: p for p in players}
    # ids who have played their 1st / 2nd preferred position at least once. Sets, because only
    # 'at least once' matters, so adding the same id again changes nothing.
    seen1, seen2 = set(), set()
    # Go through every assignment in every round and note which preferences were played
    for round_data in rounds_output:
        for a in round_data["assignments"]:
            player = by_id.get(a["player_id"])
            # Skip an assignment whose player is not in the list
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
    # Try 1 round, then 2, and so on; the first number that satisfies everyone is the minimum
    for num_rounds in range(1, max_rounds + 1):
        rounds_output = generate_rounds(players, num_rounds, num_courts)
        failed = check_guarantee_met(players, rounds_output)
        # An empty list means every player has had both positions
        if not failed:
            return rounds_output, num_rounds, []
    # The cap was reached: hand back the last attempt and who is still missing out
    return rounds_output, max_rounds, failed


# --------------------------------------------------------------------------- #
# Stress test - run with `python algorithm.py` to check a wide spread of
# roster sizes/court counts still gets a fair draw.
# --------------------------------------------------------------------------- #

def _random_roster(seed, n, demand_skew=0.0, skewed_position="GK"):
    """Makes n random test players. demand_skew is the chance a player picks skewed_position as 1st
    choice, which makes some positions very popular. The seed makes it repeatable."""
    random.seed(seed)
    players = []
    # Make each player: a 1st choice (the skewed position with chance demand_skew), then a different 2nd choice
    for i in range(n):
        if demand_skew and random.random() < demand_skew:
            pos1 = skewed_position
        else:
            pos1 = random.choice(POSITION_ORDER)
        pos2 = random.choice([p for p in POSITION_ORDER if p != pos1])
        players.append({"player_id": i + 1, "position_1": pos1, "position_2": pos2})
    return players


def _build_sweep_configs():
    """Returns the (seed, players, courts, skew) combinations used by the full stress test."""
    configs = []
    seed = 0
    # Every mix of 1 to 3 courts, five roster sizes and three skews; each gets its own seed
    for num_courts in (1, 2, 3):
        min_needed = 14 * num_courts
        for n in (14, 28, 50, 100, 150):
            # Too few players to fill the courts: skip this size
            if n < min_needed:
                continue
            for skew in (0.0, 0.3, 0.7):
                configs.append((seed, n, num_courts, skew))
                seed += 1
    return configs


def run_stress_test(quick=False):
    """Runs many random rosters through generate_minimum_rounds and prints how many met the
    guarantee and how close to the theoretical minimum they got. quick=True runs just 50."""
    # Quick mode: 50 seeds of one roster size; otherwise the full sweep
    if quick:
        configs = [(seed, 100, 2, 0.0) for seed in range(50)]
    else:
        configs = _build_sweep_configs()

    # failures = rosters that never met the guarantee; optimal = rosters drawn in the theoretical minimum rounds
    failures = 0
    optimal = 0
    max_rounds_seen = 0
    total_rounds = 0

    # Run each roster and record how it went
    for seed, n, num_courts, skew in configs:
        roster = _random_roster(seed, n, demand_skew=skew)
        rounds_output, rounds_used, failed = generate_minimum_rounds(roster, num_courts)
        lower_bound = theoretical_minimum_rounds(roster, num_courts)

        max_rounds_seen = max(max_rounds_seen, rounds_used)
        total_rounds += rounds_used
        # Drawn in the fewest rounds that are possible in theory
        if rounds_used == lower_bound:
            optimal += 1

        # Report any roster that hit the round cap
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
