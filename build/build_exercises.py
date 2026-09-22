"""
Stage 4: turn the weakness profile into the exercises you actually practise.

  python build/build_exercises.py

Builds several packs, each training a different skill:

  Your blunders     the exact positions where you went wrong. Highest signal --
                    you have already proved you don't see this.
  Punish it         your opponent erred and you let them off. Trains noticing
                    that it is your turn to win something.
  What did I allow? the position AFTER your blunder, from the other side. You
                    play the refutation against yourself, which is how you
                    learn to see it coming.
  Calculation       long forcing lines solved BLIND -- the board does not move
                    until you have entered the whole sequence. This is the one
                    that builds calculation depth rather than pattern recall.
  Endgame           technique positions from endings you actually botched.
  Themed drills     fresh Lichess puzzles on your top weaknesses, so you meet
                    the pattern often enough to internalise it.

Output: app/exercises.js  (window.EXERCISES -- loaded by the app like
        repertoire.js, so it still runs offline from a file:// URL)
"""

import json
import os
from datetime import date

import chess

import conf
import lessons as LESSONS
import lichess_puzzles as LP
import weaknesses as P
import conf
import themes as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
ANALYSIS = os.path.join(ROOT, "data", "analysis.json")
OUT = os.path.join(ROOT, "app", "exercises.js")

# Themes we never drill: the app auto-queens, so underpromotion puzzles would
# mark a correct answer wrong.
BAD_THEMES = {"underPromotion"}


# ---------------------------------------------------------------------------
# position -> the app's card format
# ---------------------------------------------------------------------------

def make_edges(start_fen, ucis, solver_color, max_plies=None):
    """Replay `ucis` from `start_fen` into the edge list the app renders.

    Mirrors exactly what build/generate.py emits for opening lines -- same
    keys, same `node.fen` nesting -- so the trainer engine in app.js can play
    a puzzle and an opening line through the identical code path.

    Returns None if the line is illegal or ends on the opponent's move (a
    puzzle must finish with the solver's move, or the last thing you do is
    watch instead of solve).
    """
    board = chess.Board(start_fen)
    edges = []
    for uci in ucis:
        if max_plies and len(edges) >= max_plies:
            break
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return None
        if move not in board.legal_moves:
            return None

        mover_is_white = board.turn == chess.WHITE
        castle = None
        if board.is_castling(move):
            rank = "1" if mover_is_white else "8"
            if chess.square_file(move.to_square) > 4:
                castle = {"from": "h" + rank, "to": "f" + rank}
            else:
                castle = {"from": "a" + rank, "to": "d" + rank}
        san = board.san(move)
        is_ep = board.is_en_passant(move)
        board.push(move)

        edges.append({
            "san": san,
            "uci": uci,
            "from": chess.square_name(move.from_square),
            "to": chess.square_name(move.to_square),
            "mine": mover_is_white == (solver_color == "white"),
            "castle": castle,
            "ep": is_ep,
            "node": {"fen": board.fen()},
        })

    # trim any trailing opponent moves -- end on the solver
    while edges and not edges[-1]["mine"]:
        edges.pop()
    if not edges or not any(e["mine"] for e in edges):
        return None
    return edges


def card(cid, start_fen, edges, meta):
    return {
        "id": cid,
        "startFen": start_fen,
        "color": meta["color"],
        "edges": edges,
        "myMoves": sum(1 for e in edges if e["mine"]),
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# packs built from your own games
# ---------------------------------------------------------------------------

def _is_fair_puzzle(e):
    """Only positions with one clearly best move make honest puzzles.

    Without this you get asked to choose between two moves the engine rates
    within a few centipawns of each other, get told you were 'wrong', and
    learn nothing.
    """
    if e["severity"] not in ("blunder", "mistake"):
        return False
    if e.get("mate_available"):
        return True
    return e["second_gap"] >= 100


def own_mistake_cards(games, cfg):
    """'You played X here and it cost you a piece — find what you missed.'"""
    picks = []
    for g in games:
        for e in g["errors"]:
            if e["is_mine"] and _is_fair_puzzle(e):
                picks.append((g, e))
    # biggest, most recent errors first
    picks.sort(key=lambda ge: (-ge[1]["cp_loss"], -(ge[0].get("end_time") or 0)))

    out, seen = [], set()
    for g, e in picks:
        if len(out) >= cfg["exercises"]["own_mistakes_max"]:
            break
        key = e["fen"].rsplit(" ", 2)[0]
        if key in seen:
            continue
        seen.add(key)

        # animate the opponent's last move in, for context
        start_fen = e.get("prev_fen") or e["fen"]
        ucis = ([e["prev_uci"]] if e.get("prev_uci") and e.get("prev_fen") else []) + e["pv"]
        edges = make_edges(start_fen, ucis, g["color"], max_plies=6)
        if not edges:
            continue
        out.append(card(f"own#{e['ply']}#{g['id'][-8:]}", start_fen, edges, {
            "color": g["color"],
            "kind": "own",
            # Retire after this many clean solves. A tactic you have solved
            # twice is a position you remember, not a pattern you have
            # learned -- the pattern is what the lessons drill.
            "maxReps": cfg["exercises"]["own_max_reps"],
            "title": "Your blunder" if e["severity"] == "blunder" else "Your mistake",
            "played": e["played"],
            "cpLoss": e["cp_loss"],
            "themes": [t for t in e["themes"] if t not in P.PHASE_TAGS],
            "gameUrl": g["url"],
            "endTime": g["end_time"],
            "moveNumber": e["move_number"],
            "opponent": g.get("opp_rating"),
            "timeClass": g["time_class"],
            "clock": e.get("clock"),
        }))
    return out


def refutation_cards(games, cfg, limit=25):
    """Play your opponent's punishment of your own blunder.

    Same position as a 'your blunder' card but seen from the other side: you
    just played the losing move, now find why it loses. Training the refutation
    is what makes you spot it before you play the move next time.
    """
    picks = []
    for g in games:
        for e in g["errors"]:
            if not e["is_mine"] or e["severity"] != "blunder":
                continue
            if "hangingPiece" not in e["themes"] and "fork" not in e["themes"]:
                continue
            picks.append((g, e))
    picks.sort(key=lambda ge: -ge[1]["cp_loss"])

    out, seen = [], set()
    other = {"white": "black", "black": "white"}
    for g, e in picks:
        if len(out) >= limit:
            break
        # position AFTER the blunder; the opponent is to move
        board = chess.Board(e["fen"])
        try:
            board.push(chess.Move.from_uci(e["played_uci"]))
        except (ValueError, AssertionError):
            continue
        after_fen = board.fen()
        key = after_fen.rsplit(" ", 2)[0]
        if key in seen:
            continue

        # we need the refutation line: re-derive from the played move's PV,
        # which analyze_games stored as the opponent's best continuation
        refutation = e.get("refutation_pv") or []
        if not refutation:
            continue
        edges = make_edges(after_fen, refutation, other[g["color"]], max_plies=4)
        if not edges:
            continue
        seen.add(key)
        out.append(card(f"ref#{e['ply']}#{g['id'][-8:]}", after_fen, edges, {
            "color": other[g["color"]],
            "kind": "refute",
            "title": "What did that allow?",
            "played": e["played"],
            "cpLoss": e["cp_loss"],
            "themes": [t for t in e["themes"] if t not in P.PHASE_TAGS],
            "gameUrl": g["url"],
            "endTime": g["end_time"],
            "moveNumber": e["move_number"],
        }))
    return out


def punish_cards(games, cfg):
    """Opponent blundered and you did not take advantage — take it now."""
    out, seen = [], set()
    picks = []
    for g in games:
        mine_by_ply = {e["ply"]: e for e in g["errors"] if e["is_mine"]}
        for e in g["errors"]:
            if e["is_mine"] or e["severity"] != "blunder":
                continue
            # the position after their blunder is where YOU had the chance
            reply = mine_by_ply.get(e["ply"] + 1)
            if not reply or not _is_fair_puzzle(reply):
                continue
            picks.append((g, e, reply))
    picks.sort(key=lambda x: -x[2]["cp_loss"])

    for g, blunder, reply in picks:
        if len(out) >= cfg["exercises"]["punish_max"]:
            break
        key = reply["fen"].rsplit(" ", 2)[0]
        if key in seen:
            continue
        seen.add(key)
        start_fen = blunder["fen"]
        ucis = [blunder["played_uci"]] + reply["pv"]
        edges = make_edges(start_fen, ucis, g["color"], max_plies=6)
        if not edges:
            continue
        out.append(card(f"pun#{reply['ply']}#{g['id'][-8:]}", start_fen, edges, {
            "color": g["color"],
            "kind": "punish",
            "title": "They just blundered",
            "played": reply["played"],
            "oppMove": blunder["played"],
            "cpLoss": reply["cp_loss"],
            "themes": [t for t in reply["themes"] if t not in P.PHASE_TAGS],
            "gameUrl": g["url"],
            "endTime": g["end_time"],
            "moveNumber": reply["move_number"],
        }))
    return out


# ---------------------------------------------------------------------------
# packs built from the Lichess database
# ---------------------------------------------------------------------------

def lichess_cards(puzzles, kind, prefix, title):
    out = []
    for p in puzzles:
        if set(p["themes"]) & BAD_THEMES:
            continue
        # Lichess convention: moves[0] is played TO you, from the given FEN.
        board = chess.Board(p["fen"])
        solver = "black" if board.turn == chess.WHITE else "white"
        edges = make_edges(p["fen"], p["moves"], solver)
        if not edges:
            continue
        out.append(card(f"{prefix}#{p['id']}", p["fen"], edges, {
            "color": solver,
            "kind": kind,
            "title": title,
            "rating": p["rating"],
            "themes": [t for t in p["themes"] if t not in P.PHASE_TAGS],
            "gameUrl": p["url"],
            "source": "lichess",
        }))
    return out


def puzzle_rating_band(prof, cfg):
    """Pick a Lichess-puzzle rating window from your chess.com rating.

    The two scales are not the same, and Lichess puzzle ratings run higher than
    a beginner's game rating. We aim slightly above your playing strength so
    the puzzles teach rather than confirm, and bundle a wide band -- the app
    then adapts within it based on how you are actually doing, which corrects
    any error in this estimate without needing a rebuild.
    """
    # The +150 guess assumes puzzle and game strength track each other, and
    # for many players they do not: solving with unlimited time and the
    # knowledge that a tactic exists is a different skill from spotting one
    # unprompted. Someone who knows their puzzle rating can state it in
    # coach_config.local.json and skip the estimate entirely.
    stated = cfg["exercises"].get("puzzle_rating")
    base = (prof.get("rating", {}) or {}).get("recent_avg") or 900
    centre = int(stated) if stated else max(600, min(2400, base + 150))
    centre = max(600, min(2800, centre))
    band = cfg["exercises"]["rating_band"]
    return centre, (max(400, centre - band), centre + band + 200)



# ---------------------------------------------------------------------------
# lessons: a diagnosis plus a progressive ladder of FRESH material
# ---------------------------------------------------------------------------

# Each rung is (id, label, rating offset from your band centre, how many).
# The offsets are what makes this deliberate practice rather than review: you
# start just below where you are, and the top rung is deliberately past it.
LADDER = [
    ("warmup",  "Same pattern, easier",  (-250, -50),  12),
    ("level",   "At your level",         (-50, 150),   20),
    ("stretch", "Past your level",       (150, 400),   12),
]


def lesson_specs(lessons, centre, cfg):
    """One puzzle-selection spec per lesson rung, in one DB pass."""
    specs = []
    for L in lessons:
        for rung, _label, (lo_off, hi_off), count in LADDER:
            shift = L.get("ratingShift", 0)
            specs.append({
                "key": f"lesson:{L['id']}:{rung}",
                "themes": set(L["themes"]),
                "rating": (max(400, centre + lo_off + shift),
                           centre + hi_off + shift),
                # ask for extra: rungs share themes, so we hand out unique
                # puzzles per lesson afterwards and need slack to do it
                "count": count * 3,
            })
    return specs


def build_lessons(data, selected, games, cfg):
    """Attach drill pools to each lesson, keeping every puzzle unique.

    Lessons overlap by theme -- three of them may all want forks -- and
    lichess_puzzles.select is deterministic, so asking twice returns the same
    puzzles. Handing them out first-come means no lesson ever drills a
    position another lesson already owns, which is what lets the app promise
    that a review is always material you have not seen.
    """
    diagnosed = LESSONS.build(data)
    if not diagnosed:
        return []

    # index your own error positions so a lesson can open with them
    by_key = {}
    for g in games:
        for e in g.get("errors") or []:
            by_key[(g["id"], e["ply"])] = (g, e)

    used = set()
    out = []
    for L in diagnosed:
        stages = []

        # rung 0 -- two of your own positions, capped at two solves each
        own_cards = []
        for ref in L.get("ownPositions", []):
            hit = by_key.get((ref["gameId"], ref["ply"]))
            if not hit:
                continue
            g, e = hit
            start_fen = e.get("prev_fen") or e["fen"]
            ucis = ([e["prev_uci"]] if e.get("prev_uci") and e.get("prev_fen")
                    else []) + e["pv"]
            edges = make_edges(start_fen, ucis, g["color"], max_plies=6)
            if not edges:
                continue
            own_cards.append(card(
                f"L-{L['id']}-own#{e['ply']}#{g['id'][-8:]}", start_fen, edges, {
                    "color": g["color"], "kind": "own",
                    "title": "From your game",
                    "played": e["played"], "cpLoss": e["cp_loss"],
                    "maxReps": cfg["exercises"]["own_max_reps"],
                    "themes": [t for t in e["themes"] if t not in P.PHASE_TAGS],
                    "gameUrl": g["url"], "endTime": g["end_time"],
                    "moveNumber": e["move_number"], "timeClass": g["time_class"],
                    "lessonId": L["id"],
                }))
        if own_cards:
            stages.append({
                "id": "own", "name": "See it in your own game",
                "blurb": "Proof this is about you, not about chess in general. "
                         "These two retire once you have solved them.",
                "cards": own_cards, "retires": True})

        # rungs 1-3 -- fresh puzzles, unique to this lesson
        for rung, label, _off, count in LADDER:
            pool = selected.get(f"lesson:{L['id']}:{rung}", [])
            fresh = [p for p in pool if p["id"] not in used][:count]
            for p in fresh:
                used.add(p["id"])
            cards = lesson_puzzle_cards(fresh, L["id"], rung, label)
            if cards:
                stages.append({
                    "id": rung, "name": label,
                    "blurb": ("Drawn from a pool -- a review gives you "
                              "positions you have not seen, not the same one "
                              "again."),
                    "cards": cards, "retires": False})

        if len(stages) < 2:
            continue
        out.append({
            "id": L["id"], "title": L["title"],
            "diagnosis": L["diagnosis"], "principle": L["principle"],
            "habit": L["habit"], "note": L.get("note"),
            "themes": L["themes"], "evidence": L["evidence"],
            "stages": stages,
        })
    return out


def lesson_puzzle_cards(puzzles, lesson_id, rung, label):
    out = []
    for p in puzzles:
        if set(p["themes"]) & BAD_THEMES:
            continue
        board = chess.Board(p["fen"])
        solver = "black" if board.turn == chess.WHITE else "white"
        edges = make_edges(p["fen"], p["moves"], solver)
        if not edges:
            continue
        out.append(card(f"L-{lesson_id}-{rung}#{p['id']}", p["fen"], edges, {
            "color": solver, "kind": "lesson", "title": label,
            "rating": p["rating"], "lessonId": lesson_id, "rung": rung,
            "themes": [t for t in p["themes"] if t not in P.PHASE_TAGS],
            "gameUrl": p["url"], "source": "lichess",
        }))
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    cfg = conf.load()
    if not os.path.exists(ANALYSIS):
        print("[FAIL] No analysis yet. Run:  python build/analyze_games.py")
        raise SystemExit(1)
    with open(ANALYSIS, encoding="utf-8") as fh:
        data = json.load(fh)

    prof = P.build(data)
    prof["openings"] = P.opening_report(data)
    with open(os.path.join(ROOT, "data", "profile.json"), "w", encoding="utf-8") as fh:
        json.dump(prof, fh, indent=2)

    games = [g for g in data["games"] if g["plies"] > 0]
    packs = []

    # ---------- 1. from your own games ----------
    own = own_mistake_cards(games, cfg)
    if own:
        packs.append({
            "id": "own-mistakes", "name": "Your own blunders", "kind": "own",
            "blurb": "Real positions from your games where you went wrong. "
                     "Find the move you missed.",
            "items": own})

    pun = punish_cards(games, cfg)
    if pun:
        packs.append({
            "id": "punish", "name": "Punish the mistake", "kind": "punish",
            "blurb": "Your opponent blundered and you let them off. "
                     "Watch their move, then take what's on offer.",
            "items": pun})

    ref = refutation_cards(games, cfg)
    if ref:
        packs.append({
            "id": "refute", "name": "What did that allow?", "kind": "refute",
            "blurb": "You just played the losing move. Now play your opponent's "
                     "side and punish it — that's how you learn to see it coming.",
            "items": ref})

    # ---------- 2. lessons + calculation ----------
    # The per-theme packs that used to live here are gone: a pack called
    # "Pins" with 35 pin puzzles tells you nothing about WHY you lose to
    # pins, and its puzzles never changed between rebuilds. Lessons replace
    # them with a diagnosis, a habit, and a rating ladder over a pool -- see
    # build/lessons.py.
    centre, (lo, hi) = puzzle_rating_band(prof, cfg)
    diagnosed = LESSONS.build(data, limit=cfg["exercises"]["lessons_max"])

    specs = lesson_specs(diagnosed, centre, cfg)
    # Calculation: long forcing lines, deliberately a bit harder than your
    # tactics band because depth is the skill being trained, not speed.
    specs.append({"key": "_calc", "themes": {"long", "veryLong"},
                  "exclude": {"oneMove"},
                  "rating": (lo, hi + 150), "count": 40})
    # Endgames: weighted toward whatever you actually reach.
    specs.append({"key": "_endgame",
                  "themes": {"endgame", "rookEndgame", "pawnEndgame", "queenEndgame"},
                  "rating": (max(400, lo - 150), hi), "count": 30})

    # The puzzle database is a big optional download. Without it you still get
    # every exercise built from your own games -- just no themed reinforcement.
    if LP.available():
        print(f"Selecting Lichess puzzles (rating {lo}-{hi}, centred {centre})")
        print(f"  lessons: {', '.join(L['id'] for L in diagnosed)}")
        selected = LP.select(specs)
    else:
        selected = {}
        print("\n[note] Lichess puzzle database not found — building only the packs\n"
              "       from your own games. Lessons will have a diagnosis and a\n"
              "       habit but no drill ladder. To add the drills, download it\n"
              "       once:\n"
              "         ./build/get_puzzle_db.sh\n")

    lesson_packs = build_lessons(data, selected, games, cfg)

    calc = lichess_cards(selected.get("_calc", []), "calc", "calc", "Calculate it out")
    calc = [c for c in calc if c["myMoves"] >= 2]
    if calc:
        packs.append({
            "id": "calculation", "name": "Calculation ladder", "kind": "calc",
            "blind": True,
            "blurb": "Multi-move forcing lines. The board does NOT move until you "
                     "have played the whole sequence — work it out in your head first.",
            "items": calc})

    endg = lichess_cards(selected.get("_endgame", []), "endgame", "end", "Endgame technique")
    if endg:
        packs.append({
            "id": "endgame", "name": "Endgame technique", "kind": "endgame",
            "blurb": "Converting won positions and holding difficult ones.",
            "items": endg})

    # ---------- 3. emit ----------
    summary = {
        "gamesAnalysed": prof.get("games_analysed", 0),
        "rating": prof.get("rating", {}),
        "acpl": prof.get("acpl"),
        "record": prof.get("record"),
        "errors": prof.get("errors"),
        "weaknesses": prof.get("weaknesses", [])[:8],
        "byPhase": prof.get("by_phase"),
        "byTimeClass": prof.get("by_time_class"),
        "timePressure": prof.get("time_pressure"),
        "punishing": prof.get("punishing"),
        "conversion": prof.get("conversion"),
        "openings": prof.get("openings"),
        "puzzleBand": {"centre": centre, "min": lo, "max": hi},
    }
    payload = {
        "generated": date.today().isoformat(),
        "username": prof.get("username"),
        "profile": summary,
        "packs": packs,
        "lessons": lesson_packs,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("// AUTO-GENERATED by build/build_exercises.py -- do not edit by hand.\n")
        fh.write("// Rebuilt from your latest chess.com games; see build/refresh.sh\n")
        fh.write("window.EXERCISES = ")
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")

    total = sum(len(p["items"]) for p in packs)
    print(f"\n[ OK ] {len(packs)} packs · {total} exercises")
    for p in packs:
        print(f"       {p['name']:<34} {len(p['items']):>4}")

    drills = sum(len(s["cards"]) for L in lesson_packs for s in L["stages"])
    print(f"\n[ OK ] {len(lesson_packs)} lessons · {drills} drill positions")
    for L in lesson_packs:
        rungs = " ".join(f"{s['id']}:{len(s['cards'])}" for s in L["stages"])
        print(f"       {L['title'][:44]:<46} {rungs}")
    print(f"\nWrote {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
