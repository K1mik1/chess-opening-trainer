"""
Stage 3: turn the raw analysis into a picture of how you actually play.

  python build/weaknesses.py            # print the report
  python build/weaknesses.py --json     # machine-readable

This is the part that decides what you practise. It answers:

  * Which tactical patterns do you keep getting wrong, and how much do they
    cost you? (ranked by damage, not just frequency -- hanging a queen twice
    matters more than ten small inaccuracies)
  * When in the game do you go wrong -- opening, middlegame, endgame?
  * Do your blunders cluster when the clock gets low?
  * How often do you fail to punish your opponent's mistakes?
  * Where do you leave your own opening repertoire, and what do you face most?

Nothing here calls the engine; it all reads data/analysis.json.
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict

import chess

import themes as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
ANALYSIS = os.path.join(ROOT, "data", "analysis.json")
OUT = os.path.join(ROOT, "data", "profile.json")

# Themes that describe *when* rather than *what* -- useful context, but not
# something you can drill, so they never appear as a "weakness to practise".
PHASE_TAGS = {"opening", "middlegame", "endgame", "rookEndgame", "pawnEndgame",
              "queenEndgame", "knightEndgame", "bishopEndgame", "exposedKing"}


def base_seconds(time_control):
    """'600' -> 600 · '180+2' -> 180 · '1/86400' (daily) -> 86400."""
    if not time_control:
        return None
    tc = str(time_control)
    if tc.startswith("1/"):
        return int(tc[2:])
    m = re.match(r"^(\d+)", tc)
    return int(m.group(1)) if m else None


def build(data):
    games = data["games"]
    played = [g for g in games if g["plies"] > 0]

    prof = {
        "username": data.get("username"),
        "games_analysed": len(played),
    }
    if not played:
        return prof

    # ---------------- record & rating ----------------
    wins = sum(1 for g in played if g["result"] == "win")
    draws = sum(1 for g in played if g["result"] in
                ("agreed", "repetition", "stalemate", "insufficient",
                 "50move", "timevsinsufficient"))
    prof["record"] = {"win": wins, "loss": len(played) - wins - draws, "draw": draws}

    ratings = [g["my_rating"] for g in played if g.get("my_rating")]
    prof["rating"] = {
        "current": ratings[-1] if ratings else None,
        "recent_avg": round(sum(ratings[-25:]) / len(ratings[-25:])) if ratings else None,
        "trend": (round(sum(ratings[-15:]) / len(ratings[-15:]))
                  - round(sum(ratings[:15]) / len(ratings[:15]))) if len(ratings) >= 30 else None,
    }
    by_class = defaultdict(list)
    for g in played:
        by_class[g["time_class"]].append(g)
    prof["by_time_class"] = {
        k: {"games": len(v),
            "acpl": round(sum(x["acpl"] for x in v) / len(v), 1),
            "win_rate": round(sum(1 for x in v if x["result"] == "win") / len(v) * 100)}
        for k, v in sorted(by_class.items(), key=lambda kv: -len(kv[1]))
    }
    prof["acpl"] = round(sum(g["acpl"] for g in played) / len(played), 1)

    # ---------------- my errors ----------------
    my_errors = [dict(e, _game=g) for g in played for e in g["errors"] if e["is_mine"]]
    opp_errors = [dict(e, _game=g) for g in played for e in g["errors"] if not e["is_mine"]]

    my_moves = sum(g["plies"] for g in played) / 2 or 1
    sev = Counter(e["severity"] for e in my_errors)
    prof["errors"] = {
        "blunders": sev["blunder"],
        "mistakes": sev["mistake"],
        "inaccuracies": sev["inaccuracy"],
        "blunders_per_game": round(sev["blunder"] / len(played), 2),
        "blunders_per_100_moves": round(sev["blunder"] / my_moves * 100, 1),
    }

    # ---------------- theme ranking (the core output) ----------------
    # Rank by total centipawns lost, not raw count: the point is to fix what is
    # actually costing you games. Only serious errors count toward a weakness --
    # an inaccuracy is not a pattern you need to drill.
    serious = [e for e in my_errors if e["severity"] in ("blunder", "mistake")]
    dmg = defaultdict(int)
    cnt = Counter()
    for e in serious:
        for t in e["themes"]:
            if t in PHASE_TAGS:
                continue
            dmg[t] += e["cp_loss"]
            cnt[t] += 1
    total_dmg = sum(dmg.values()) or 1
    weaknesses = [{
        "theme": t,
        "label": T.LABELS.get(t, t),
        "count": cnt[t],
        "cp_lost": dmg[t],
        "share": round(dmg[t] / total_dmg * 100, 1),
        "avg_loss": round(dmg[t] / cnt[t]),
    } for t in sorted(dmg, key=lambda x: -dmg[x])]
    prof["weaknesses"] = weaknesses

    # ---------------- where in the game ----------------
    phase_dmg = defaultdict(int)
    phase_cnt = Counter()
    for e in serious:
        phase = next((t for t in e["themes"] if t in
                      ("opening", "middlegame", "endgame")), "middlegame")
        phase_dmg[phase] += e["cp_loss"]
        phase_cnt[phase] += 1
    prof["by_phase"] = {p: {"count": phase_cnt[p], "cp_lost": phase_dmg[p]}
                        for p in ("opening", "middlegame", "endgame")}

    buckets = Counter()
    for e in serious:
        b = min(50, (e["move_number"] // 10) * 10)
        buckets[b] += 1
    prof["by_move_number"] = {str(k): buckets[k] for k in sorted(buckets)}

    # ---------------- time trouble ----------------
    # Bucket each blunder by how much of the original clock was left. If the
    # bottom bucket is much worse than the top, the fix is pacing, not tactics.
    tt = defaultdict(lambda: {"moves": 0, "blunders": 0})
    for g in played:
        # Daily games budget time PER MOVE, so a "low clock" there means
        # nothing like it does in a real-time game. Including them would
        # invent a time-trouble problem that isn't there.
        if g.get("time_class") == "daily":
            continue
        base = base_seconds(g.get("time_control"))
        if not base:
            continue
        for e in g["errors"]:
            if not e["is_mine"] or e.get("clock") is None:
                continue
            frac = e["clock"] / base
            key = ("under 10%" if frac < 0.10 else "10-25%" if frac < 0.25
                   else "25-50%" if frac < 0.50 else "over 50%")
            tt[key]["moves"] += 1
            if e["severity"] == "blunder":
                tt[key]["blunders"] += 1
    prof["time_pressure"] = {
        k: {"flagged_moves": v["moves"], "blunders": v["blunders"],
            "blunder_share": round(v["blunders"] / v["moves"] * 100) if v["moves"] else 0}
        for k, v in sorted(tt.items(),
                           key=lambda kv: ["under 10%", "10-25%", "25-50%",
                                           "over 50%"].index(kv[0]))
    }

    # ---------------- missed punishes ----------------
    # Your opponent blundered; did the very next move take advantage? We count
    # a miss when your reply was itself flagged as an error.
    missed = 0
    for g in played:
        errs = {e["ply"]: e for e in g["errors"]}
        for e in g["errors"]:
            if e["is_mine"] or e["severity"] != "blunder":
                continue
            reply = errs.get(e["ply"] + 1)
            if reply and reply["is_mine"]:
                missed += 1
    opp_blunders = sum(1 for e in opp_errors if e["severity"] == "blunder")
    prof["punishing"] = {
        "opponent_blunders": opp_blunders,
        "missed": missed,
        "conversion_rate": round((opp_blunders - missed) / opp_blunders * 100)
        if opp_blunders else None,
    }

    # ---------------- endgame conversion ----------------
    # Games you were clearly winning at some point but did not win. The engine
    # only flags errors, so "was winning" is inferred from a position where the
    # best move was worth a lot and the game still slipped away.
    blown = 0
    for g in played:
        if g["result"] == "win":
            continue
        peak = max((e["cp_best"] for e in g["errors"] if e["is_mine"]), default=None)
        if peak is not None and peak >= 300:
            blown += 1
    prof["conversion"] = {
        "games_not_won": len(played) - wins,
        "was_winning_but_did_not_win": blown,
    }

    return prof


# ---------------------------------------------------------------------------
# opening leaks -- needs the ECO book and your repertoire
# ---------------------------------------------------------------------------

def opening_report(data, limit_openings=8):
    """Which openings you actually meet, and where you leave known theory."""
    try:
        from generate import load_eco
    except Exception:
        return {}
    book_epds, name_by_epd = load_eco()

    faced = Counter()
    exit_plies = []
    per_opening = defaultdict(lambda: {"games": 0, "exits": [], "score": 0})

    for g in data["games"]:
        sans = g.get("opening_sans") or []
        if not sans:
            continue
        board = chess.Board()
        name = None
        exit_ply = None
        for i, san in enumerate(sans):
            try:
                board.push_san(san)
            except ValueError:
                break
            if board.epd() in book_epds:
                name = name_by_epd.get(board.epd(), name)
            elif exit_ply is None:
                exit_ply = i
                break
        label = name or "Unnamed"
        # collapse "Italian Game: Giuoco Pianissimo, Main line" -> "Italian Game"
        family = label.split(":")[0].strip()
        faced[family] += 1
        rec = per_opening[family]
        rec["games"] += 1
        if exit_ply is not None:
            rec["exits"].append(exit_ply)
            exit_plies.append(exit_ply)
        rec["score"] += 1 if g["result"] == "win" else 0

    out = []
    for family, n in faced.most_common(limit_openings):
        rec = per_opening[family]
        out.append({
            "opening": family,
            "games": rec["games"],
            "win_rate": round(rec["score"] / rec["games"] * 100),
            "avg_book_exit_move": round(sum(rec["exits"]) / len(rec["exits"]) / 2 + 1, 1)
            if rec["exits"] else None,
        })
    return {
        "most_faced": out,
        "avg_book_exit_move": round(sum(exit_plies) / len(exit_plies) / 2 + 1, 1)
        if exit_plies else None,
    }


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def print_report(p):
    if not p.get("games_analysed"):
        print("No analysed games yet.")
        return
    r, rt = p["record"], p["rating"]
    print(f"\n{'='*66}")
    print(f"  HOW YOU HAVE BEEN PLAYING — {p['username']}")
    print(f"{'='*66}\n")
    print(f"  {p['games_analysed']} games   {r['win']}W / {r['loss']}L / {r['draw']}D"
          f"   ·   rating now {rt['current']}"
          + (f"  ({rt['trend']:+d} over the sample)" if rt.get("trend") else ""))
    print(f"  Average centipawn loss: {p['acpl']}   "
          f"(lower is better; ~80+ is typical under 1200)")
    print(f"  Blunders: {p['errors']['blunders']}  "
          f"({p['errors']['blunders_per_game']}/game, "
          f"{p['errors']['blunders_per_100_moves']} per 100 moves)\n")

    print(f"  {'BY TIME CONTROL':<20}{'games':>7}{'ACPL':>8}{'win%':>7}")
    for k, v in p["by_time_class"].items():
        print(f"  {k:<20}{v['games']:>7}{v['acpl']:>8}{v['win_rate']:>7}")

    print(f"\n  YOUR TOP LEAKS (ranked by centipawns thrown away)")
    if not p["weaknesses"]:
        print("    — not enough serious errors in the sample yet —")
    for w in p["weaknesses"][:8]:
        bar = "█" * max(1, round(w["share"] / 3))
        print(f"    {w['label']:<34} {w['count']:>3}×  {w['share']:>5.1f}%  {bar}")

    print(f"\n  WHEN YOU GO WRONG")
    for phase, v in p["by_phase"].items():
        print(f"    {phase:<14} {v['count']:>3} serious errors   {v['cp_lost']:>6} cp lost")

    if p.get("time_pressure"):
        print(f"\n  CLOCK PRESSURE (share of your flagged moves that were blunders)")
        for k, v in p["time_pressure"].items():
            print(f"    {k:<12} {v['blunder_share']:>3}%   ({v['blunders']}/{v['flagged_moves']})")

    pu = p["punishing"]
    if pu["opponent_blunders"]:
        print(f"\n  PUNISHING MISTAKES")
        print(f"    Opponents blundered {pu['opponent_blunders']}× — you converted "
              f"{pu['conversion_rate']}% of them ({pu['missed']} missed).")

    cv = p["conversion"]
    if cv["was_winning_but_did_not_win"]:
        print(f"\n  CONVERSION")
        print(f"    {cv['was_winning_but_did_not_win']} games you were clearly winning "
              f"and did not win.")

    op = p.get("openings") or {}
    if op.get("most_faced"):
        print(f"\n  OPENINGS YOU ACTUALLY MEET")
        for o in op["most_faced"][:6]:
            exit_at = f"leave book ~move {o['avg_book_exit_move']}" \
                if o["avg_book_exit_move"] else "stay in book"
            print(f"    {o['opening']:<32} {o['games']:>3} games  "
                  f"{o['win_rate']:>3}% won   {exit_at}")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(ANALYSIS):
        print("[FAIL] No analysis yet. Run:  python build/analyze_games.py")
        raise SystemExit(1)
    with open(ANALYSIS, encoding="utf-8") as fh:
        data = json.load(fh)

    prof = build(data)
    prof["openings"] = opening_report(data)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(prof, fh, indent=2)

    if args.json:
        print(json.dumps(prof, indent=2))
    else:
        print_report(prof)
        print(f"  (also written to {OUT})\n")


if __name__ == "__main__":
    main()
