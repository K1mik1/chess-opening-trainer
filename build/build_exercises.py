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
    base = (prof.get("rating", {}) or {}).get("recent_avg") or 900
    centre = max(600, min(2400, base + 150))
    band = cfg["exercises"]["rating_band"]
    return centre, (max(400, centre - band), centre + band + 200)


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

    # ---------- 2. themed reinforcement + calculation ----------
    centre, (lo, hi) = puzzle_rating_band(prof, cfg)
    top = [w["theme"] for w in prof.get("weaknesses", [])
           if w["theme"] not in P.PHASE_TAGS][:cfg["exercises"]["lichess_themes_tracked"]]
    # Always cover the fundamentals, even in a clean sample.
    for fallback in ("hangingPiece", "fork", "pin"):
        if fallback not in top:
            top.append(fallback)
    top = top[:cfg["exercises"]["lichess_themes_tracked"]]

    specs = [{"key": t, "themes": {t}, "rating": (lo, hi),
              "count": cfg["exercises"]["lichess_per_theme"]} for t in top]
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
        print(f"  themes: {', '.join(top)}")
        selected = LP.select(specs)
    else:
        selected = {}
        print("\n[note] Lichess puzzle database not found — building only the packs\n"
              "       from your own games. To add themed drills, calculation and\n"
              "       endgame practice, download it once:\n"
              "         ./build/get_puzzle_db.sh\n")

    for t in top:
        items = lichess_cards(selected.get(t, []), "theme", f"lc-{t}", T.LABELS.get(t, t))
        if items:
            w = next((x for x in prof.get("weaknesses", []) if x["theme"] == t), None)
            blurb = (f"{w['count']} serious errors from this pattern in your games "
                     f"({w['share']}% of everything you lost)."
                     if w else "A fundamental pattern worth keeping sharp.")
            packs.append({"id": f"theme-{t}", "name": T.LABELS.get(t, t),
                          "kind": "theme", "theme": t, "blurb": blurb, "items": items})

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
    print(f"\nWrote {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
