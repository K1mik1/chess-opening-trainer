"""
Which openings you meet that your repertoire has no answer for.

  python3 build/gaps.py

The opening trainer can only help with positions it teaches. This finds the
positions it does NOT teach, ranked by how much they are actually costing you:
how often you reach them, how you score there, and how far off the rails the
game goes afterwards.

The ranking deliberately weights recent games far more heavily (60-day
half-life, same as priority.py). What you met in March is history; what you met
last week is your next game.

This only reports. Turning a gap into lines you drill every morning is
build/derive_lines.py, and adding the course is a decision you make by hand --
the repertoire is small on purpose, and a course you do not need is time taken
from one you do.
"""

import collections
import datetime
import json
import os

import chess

import conf
import priority

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.join(HERE, os.pardir, "data", "analysis.json")

# How deep into the game an "opening gap" can be. Past about move 6 you are
# out of anybody's book and the problem is chess, not preparation.
MAX_PLY = 12
MIN_GAMES = 3


def covered_prefixes(repertoire):
    """color -> list of SAN-lists the repertoire already answers."""
    out = {"white": [], "black": []}
    for course in repertoire:
        for pre in course.get("match", []):
            out[course["color"]].append((pre.split(), course["id"]))
    return out


# An opening counts as "current" if you have met it inside your most recent
# RECENT_WINDOW games. Measuring staleness in days instead breaks whenever you
# take a fortnight off -- everything looks abandoned. Measuring it in games
# asks the question you actually care about: is this still happening to me?
RECENT_WINDOW = 40


def find_gaps(games, repertoire):
    cov = covered_prefixes(repertoire)
    now = max((g.get("end_time") or 0) for g in games) or 0
    recent_ids = {g["id"] for g in
                  sorted(games, key=lambda g: -(g.get("end_time") or 0))[:RECENT_WINDOW]}

    buckets = collections.defaultdict(
        lambda: {"games": 0, "recent": 0.0, "wins": 0, "acpl": [],
                 "last": 0, "in_recent": 0,
                 "next": collections.Counter(), "examples": []})

    for g in games:
        color = g.get("color")
        sans = (g.get("opening_sans") or [])[:MAX_PLY]
        if not sans:
            continue
        if any(len(p) <= len(sans) and sans[:len(p)] == p for p, _ in cov[color]):
            continue

        # Split the gap at the exact move that left coverage: find the longest
        # prefix of this game that any course still agrees with, then take one
        # move more. That single move IS the gap -- bucketing any shallower
        # merges openings that need completely different answers (Philidor,
        # Petrov and the Elephant Gambit all share "e4 e5 Nf3").
        depth = 0
        for p, _ in cov[color]:
            common = 0
            for a, b in zip(sans, p):
                if a != b:
                    break
                common += 1
            depth = max(depth, common)
        if depth >= len(sans):
            continue
        key = " ".join(sans[:depth + 1])

        age = max(0.0, (now - (g.get("end_time") or now)) / 86400.0)
        b = buckets[(color, key)]
        b["games"] += 1
        b["recent"] += 0.5 ** (age / priority.HALF_LIFE_DAYS)
        if g.get("result") == "win":
            b["wins"] += 1
        b["acpl"].append(g.get("acpl") or 0)
        b["last"] = max(b["last"], g.get("end_time") or 0)
        if g["id"] in recent_ids:
            b["in_recent"] += 1
        if len(sans) > depth + 1:
            b["next"][sans[depth + 1]] += 1
        if len(b["examples"]) < 3:
            b["examples"].append(" ".join(sans[:8]))

    rows = []
    for (color, key), b in buckets.items():
        if b["games"] < MIN_GAMES:
            continue
        rows.append({
            "color": color, "line": key,
            "last": b["last"],
            "in_recent": b["in_recent"],
            "stale": b["in_recent"] == 0,
            "games": b["games"], "recent": round(b["recent"], 2),
            "win_rate": round(100 * b["wins"] / b["games"]),
            "acpl": round(sum(b["acpl"]) / len(b["acpl"]), 1),
            "next": b["next"].most_common(5),
            "examples": b["examples"],
        })
    # Cost = how often you get there x how badly it goes -- but an opening you
    # have stopped playing costs you nothing, whatever the history says, so it
    # sorts below everything current rather than merely being discounted.
    rows.sort(key=lambda r: (r["stale"],
                             -(r["recent"] * (1.0 + (50 - r["win_rate"]) / 100.0))))
    return rows


def main():
    from repertoire import REPERTOIRE
    with open(ANALYSIS, encoding="utf-8") as fh:
        games = json.load(fh)["games"]

    rows = find_gaps(games, REPERTOIRE)
    print(f"\nUNANSWERED OPENINGS  ({len(rows)} with >= {MIN_GAMES} games)\n")
    print(f"  {'':<5} {'line':<26} {'games':>5} {'won':>5} {'acpl':>6} "
          f"{'last met':>11} {'recent':>7}   most common continuation")
    for r in rows:
        nxt = ", ".join(f"{s}({n})" for s, n in r["next"][:4])
        when = (datetime.date.fromtimestamp(r["last"]).isoformat()
                if r["last"] else "?")
        recent = f"{r['in_recent']}/{RECENT_WINDOW}" if not r["stale"] else "none *"
        print(f"  {r['color'][:1].upper():<5} {r['line']:<26} {r['games']:>5} "
              f"{r['win_rate']:>4}% {r['acpl']:>6.1f} {when:>11} {recent:>7}   {nxt}")
    if any(r["stale"] for r in rows):
        print(f"\n  * you have not met this in your last {RECENT_WINDOW} games "
              f"-- an opening you have\n    stopped playing, or one your "
              f"opponents stopped playing. Not worth a course.\n    (Recency "
              f"weighting alone misses these: 20 games in the spring still\n"
              f"    outweighs 5 last month. Hence the column.)")

    if rows and not all(r["stale"] for r in rows):
        print("\n  Next step: build/derive_lines.py turns one of these into "
              "lines\n  (their real moves, your sound answers), ready to paste "
              "into repertoire.py.")


if __name__ == "__main__":
    main()
