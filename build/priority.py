"""
How much of your practice time each opening deserves.

The trainer used to introduce new lines in a fixed hand-written order (tier 1
before tier 2). That is a reasonable curriculum for a stranger, and the wrong
one for you: it spent your mornings on openings you had not met in months while
the ones you actually lose to were not in the repertoire at all.

This module replaces the fixed order with a number computed from your real
games, recomputed on every fortnightly refresh. Three inputs:

  frequency   how often you ACTUALLY reach the opening, recency-weighted with a
              60-day half-life. An opening you played twice last week outranks
              one you played twenty times in March -- which is what you want,
              because repertoires drift and yours has.

  results     how you do once you get there. An opening you meet often AND
              score badly in is the best possible use of study time; one you
              already win 65% of is maintenance. This is the part that makes
              the weighting coach-like rather than merely descriptive.

  pinning     openings you have explicitly said you want to train get a floor
              under their weight, so your stated intent always beats the data.
              PINNED, below, is that list.

A course is matched to your games by MOVE PREFIX (see `match` in
repertoire.py), not by ECO family name. Family names are too coarse -- "King's
Pawn Game" covers 2.Qh5, 2.d3 and 2.Bc4, which need completely different
answers -- and this way a course claims exactly the games it actually prepares
you for.

Everything degrades safely: with no analysis on disk (a fresh clone, or the
opening trainer used on its own) every course falls back to the static weight
declared in repertoire.py, and the app behaves as it always did.
"""

import json
import math
import os

import chess

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.join(HERE, os.pardir, "data", "analysis.json")

# Recency half-life. 60 days is roughly "the last two months count double the
# two before that" -- long enough to be stable across a fortnightly refresh,
# short enough to notice when you change what you play.
HALF_LIFE_DAYS = 60

# Openings the user has explicitly asked to prioritise. Their computed weight
# is floored at PIN_FLOOR so a quiet fortnight cannot demote them.
PINNED = {
    # White
    "scotch", "ruy_lopez", "italian",
    # Black
    "petrov", "caro_kann", "slav",
}
PIN_FLOOR = 1.45

# A course you have never once reached still gets a little weight -- it is in
# the repertoire for a reason -- but it should not crowd out live material.
UNMET_WEIGHT = 0.30


def _load_games():
    if not os.path.exists(ANALYSIS):
        return []
    try:
        with open(ANALYSIS, encoding="utf-8") as fh:
            return json.load(fh).get("games", [])
    except (OSError, ValueError):
        return []


def _prefix_plies(prefix):
    """'e4 e5 Nf3 Nc6 d4' -> the list of SANs, validated as legal."""
    board = chess.Board()
    sans = prefix.split()
    for san in sans:
        board.push_san(san)          # raises if the prefix itself is nonsense
    return sans


def _matches(game_sans, prefix_sans):
    if len(game_sans) < len(prefix_sans):
        return False
    return game_sans[:len(prefix_sans)] == prefix_sans


def measure(repertoire, games=None):
    """Per course: recency-weighted games, win rate, ACPL. Pure measurement."""
    games = _load_games() if games is None else games
    if not games:
        return {}, {}

    now = max((g.get("end_time") or 0) for g in games) or 0
    overall_acpl = (sum(g.get("acpl") or 0 for g in games) / len(games)) or 1.0

    stats = {}
    for course in repertoire:
        prefixes = [_prefix_plies(p) for p in course.get("match", [])]
        if not prefixes:
            continue
        wsum = n = wins = 0.0
        acpls = []
        for g in games:
            if g.get("color") != course["color"]:
                continue
            sans = g.get("opening_sans") or []
            if not any(_matches(sans, p) for p in prefixes):
                continue
            age_days = max(0.0, (now - (g.get("end_time") or now)) / 86400.0)
            recency = 0.5 ** (age_days / HALF_LIFE_DAYS)
            wsum += recency
            n += 1
            if g.get("result") == "win":
                wins += 1
            acpls.append(g.get("acpl") or overall_acpl)
        if n:
            stats[course["id"]] = {
                "games": int(n),
                "recent": round(wsum, 2),
                "win_rate": round(100.0 * wins / n),
                "acpl": round(sum(acpls) / len(acpls), 1),
            }
    return stats, {"overall_acpl": round(overall_acpl, 1), "games": len(games)}


def course_weights(repertoire, games=None):
    """id -> {weight, why, ...}. The number the app schedules on."""
    stats, meta = measure(repertoire, games)

    # Recency mass is normalised per colour: you play roughly half your games
    # with each, and a White course should not outrank a Black one merely
    # because you happened to get more White games in the sample.
    total_by_color = {"white": 0.0, "black": 0.0}
    for course in repertoire:
        s = stats.get(course["id"])
        if s:
            total_by_color[course["color"]] += s["recent"]

    out = {}
    for course in repertoire:
        cid = course["id"]
        static = float(course.get("weight", 1.0))
        s = stats.get(cid)

        if not s or not total_by_color[course["color"]]:
            weight = static if not stats else UNMET_WEIGHT * static
            why = ("no analysis yet" if not stats
                   else "not reached in your recent games")
            out[cid] = {"weight": round(weight, 3),
                        "raw": round(weight, 3), "why": why}
            continue

        share = s["recent"] / total_by_color[course["color"]]

        # Frequency term: a course covering a third of your games as that
        # colour lands near 1.4; one covering 2% lands near 0.4.
        frequency = 0.35 + 3.0 * share

        # Urgency: losing, or playing sloppily, in an opening you meet often is
        # the strongest signal there is that it deserves the morning slot.
        win_gap = (50 - s["win_rate"]) / 100.0            # +0.28 at 22% won
        acpl_gap = (s["acpl"] - meta["overall_acpl"]) / max(meta["overall_acpl"], 1)
        urgency = 1.0 + 1.4 * win_gap + 0.5 * acpl_gap
        urgency = max(0.65, min(1.9, urgency))

        raw = frequency * urgency
        pinned = cid in PINNED
        # A pin is a floor, not a value: it guarantees the opening keeps its
        # place in the rotation without discarding what the games say. Keeping
        # `raw` lets the caller order pinned courses among themselves by merit
        # instead of leaving six of them tied at exactly PIN_FLOOR.
        weight = max(raw, PIN_FLOOR) if pinned else raw

        bits = [f"{s['games']} games", f"{s['win_rate']}% won"]
        if s["acpl"] > meta["overall_acpl"] + 5:
            bits.append(f"acpl {s['acpl']} (above your {meta['overall_acpl']})")
        if pinned and weight > raw:
            bits.append("pinned")
        out[cid] = {
            "weight": round(weight, 3),
            "raw": round(raw, 3),
            "why": " · ".join(bits),
            "games": s["games"],
            "winRate": s["win_rate"],
            "acpl": s["acpl"],
        }
    return out


if __name__ == "__main__":
    from repertoire import REPERTOIRE
    w = course_weights(REPERTOIRE)
    for cid, rec in sorted(w.items(), key=lambda kv: -kv[1]["weight"]):
        course = next(c for c in REPERTOIRE if c["id"] == cid)
        print(f"{rec['weight']:5.2f}  {course['color'][0]}  "
              f"{course['name']:<40} {rec['why']}")
