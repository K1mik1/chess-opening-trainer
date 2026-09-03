"""
Write repertoire lines for the openings you meet but have no answer to.

  python3 build/derive_lines.py            # every spec below
  python3 build/derive_lines.py philidor   # just one

gaps.py finds the holes; this fills them. For each hole it grows a small tree:

  YOUR moves        the move YOU already play there, if Stockfish agrees it is
                    within TOLERANCE of best -- otherwise the move that fixes
                    it, flagged in a comment. A coach does not rewrite what is
                    working: vs 1.e3 you play 1...e5 and score 75%, so the
                    course teaches 1...e5, not the engine's marginal preference.
                    Only genuinely wrong moves get corrected.

  OPPONENT moves    the moves YOUR opponents actually played in that exact
                    position, most common first, taken from your own game
                    history. Falls back to Stockfish's choice once your games
                    run out.

That second half is the point. A book written for masters answers the moves
masters play. At 800 you need the answer to 2.Qh5, and you need it against the
follow-up the 800-rated player in front of you will actually choose. Both come
straight out of your history.

Output is pasteable Python for repertoire.py. Nothing is written automatically:
lines get eyeballed before they become something you drill every morning.
"""

import collections
import json
import os
import sys

import chess
import chess.engine

import conf
from analyze_games import find_engine

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.join(HERE, os.pardir, "data", "analysis.json")

DEPTH = 20

# How far your own move may fall short of the engine's before the course
# overrules it. 30cp is inside the noise for an opening move.
TOLERANCE = 30

# root         where the gap starts (ends on the opponent's committal move)
# plies        how long each finished line should be
# branch       how many opponent alternatives to follow at the first
#              opponent decision after the root; 1 = a single main line
SPECS = [
    # ---------------- White ----------------
    {"id": "philidor",      "color": "white", "root": "e4 e5 Nf3 d6",
     "plies": 12, "branch": 2},
    {"id": "elephant",      "color": "white", "root": "e4 e5 Nf3 d5",
     "plies": 10, "branch": 2},
    {"id": "e5_busch",      "color": "white", "root": "e4 e5 Nf3 Bc5",
     "plies": 10, "branch": 1},
    {"id": "e5_qf6",        "color": "white", "root": "e4 e5 Nf3 Qf6",
     "plies": 10, "branch": 1},
    {"id": "petrov_white",  "color": "white", "root": "e4 e5 Nf3 Nf6",
     "plies": 12, "branch": 2},
    {"id": "caro_white",    "color": "white", "root": "e4 c6",
     "plies": 12, "branch": 2},
    {"id": "modern_white",  "color": "white", "root": "e4 g6",
     "plies": 10, "branch": 1},
    {"id": "pirc_white",    "color": "white", "root": "e4 d6",
     "plies": 10, "branch": 1},

    # ---------------- Black: 1.e4 e5 sidelines ----------------
    {"id": "e5_qh5",        "color": "black", "root": "e4 e5 Qh5",
     "plies": 10, "branch": 1},
    {"id": "e5_qf3",        "color": "black", "root": "e4 e5 Qf3",
     "plies": 10, "branch": 1},
    {"id": "e5_d3",         "color": "black", "root": "e4 e5 d3",
     "plies": 10, "branch": 2},
    {"id": "e5_bc4",        "color": "black", "root": "e4 e5 Bc4",
     "plies": 10, "branch": 2},
    {"id": "e5_nc3",        "color": "black", "root": "e4 e5 Nc3",
     "plies": 10, "branch": 2},
    {"id": "e5_centre",     "color": "black", "root": "e4 e5 d4",
     "plies": 10, "branch": 2},
    {"id": "e5_kg",         "color": "black", "root": "e4 e5 f4",
     "plies": 10, "branch": 1},

    # ---------------- Black: Petrov sidelines ----------------
    {"id": "petrov_d3",     "color": "black", "root": "e4 e5 Nf3 Nf6 d3",
     "plies": 12, "branch": 2},
    {"id": "petrov_bc4",    "color": "black", "root": "e4 e5 Nf3 Nf6 Bc4",
     "plies": 12, "branch": 2},

    # ---------------- Black: Caro-Kann sidelines ----------------
    {"id": "caro_nc3",      "color": "black", "root": "e4 c6 Nc3",
     "plies": 10, "branch": 2},
    {"id": "caro_d3",       "color": "black", "root": "e4 c6 d3",
     "plies": 10, "branch": 1},
    {"id": "caro_bc4",      "color": "black", "root": "e4 c6 Bc4",
     "plies": 10, "branch": 1},
    {"id": "caro_qf3",      "color": "black", "root": "e4 c6 Qf3",
     "plies": 10, "branch": 1},
    {"id": "caro_nf3",      "color": "black", "root": "e4 c6 Nf3",
     "plies": 10, "branch": 1},

    # ---------------- Black: 1.d4 without c4 ----------------
    {"id": "london_black",  "color": "black", "root": "d4 d5 Bf4",
     "plies": 12, "branch": 2},
    {"id": "d4_nf3",        "color": "black", "root": "d4 d5 Nf3",
     "plies": 12, "branch": 2},
    {"id": "jobava_black",  "color": "black", "root": "d4 d5 Nc3",
     "plies": 10, "branch": 1},
    {"id": "colle_black",   "color": "black", "root": "d4 d5 e3",
     "plies": 10, "branch": 1},

    # ---------------- Black: flank openings ----------------
    {"id": "flank_nf3",     "color": "black", "root": "Nf3",
     "plies": 10, "branch": 2},
    {"id": "flank_e3",      "color": "black", "root": "e3",
     "plies": 10, "branch": 1},
    {"id": "flank_c4",      "color": "black", "root": "c4",
     "plies": 10, "branch": 1},
    {"id": "flank_b3",      "color": "black", "root": "b3",
     "plies": 10, "branch": 1},
]


def opponent_book(games):
    """EPD -> Counter of the SANs played from it across your games."""
    book = collections.defaultdict(collections.Counter)
    for g in games:
        board = chess.Board()
        for san in (g.get("opening_sans") or [])[:20]:
            try:
                move = board.parse_san(san)
            except ValueError:
                break
            book[board.epd()][san] += 1
            board.push(move)
    return book


def derive(spec, eng, book):
    mine = chess.WHITE if spec["color"] == "white" else chess.BLACK
    limit = chess.engine.Limit(depth=DEPTH)
    lines = []
    tags = []

    def opponent_choices(board, allowed):
        """Their real moves here, most common first; engine best as backup."""
        out = []
        for san, _n in book.get(board.epd(), collections.Counter()).most_common():
            try:
                board.parse_san(san)
            except ValueError:
                continue
            out.append(san)
            if len(out) >= allowed:
                break
        if not out:
            info = eng.analyse(board, limit)
            out = [board.san(info["pv"][0])]
        return out

    def my_move(board):
        """Your move here -- yours if it is already sound, else the fix.

        A coach does not rewrite a move that is working. If what you actually
        play in this position is within TOLERANCE of the engine's best, you
        keep it: the repertoire stays yours, and the only moves it corrects are
        the ones that are genuinely wrong. Returns (move, tag) where tag is
        'yours' when we kept your move and 'fix' when we overruled it.
        """
        info = eng.analyse(board, limit)
        best = info["pv"][0]
        best_cp = info["score"].pov(board.turn).score(mate_score=10000)
        for san, _n in book.get(board.epd(), collections.Counter()).most_common(3):
            try:
                mv = board.parse_san(san)
            except ValueError:
                continue
            if mv == best:
                return best, "yours"
            got = eng.analyse(board, limit, root_moves=[mv])
            cp = got["score"].pov(board.turn).score(mate_score=10000)
            if best_cp - cp <= TOLERANCE:
                return mv, "yours"
            # your usual move here actually loses something -- overrule it,
            # and remember that this is a move worth flagging in the course.
            return best, f"fix:{board.san(mv)}"
        return best, "new"

    def walk(board, sans, budget):
        if len(sans) >= spec["plies"] or board.is_game_over():
            lines.append((list(sans), list(tags)))
            return
        if board.turn == mine:
            move, tag = my_move(board)
            san = board.san(move)
            tags.append(f"{len(sans)+1}.{san} {tag}" if tag != "yours" else "")
            board.push(move)
            walk(board, sans + [san], budget)
            board.pop()
            tags.pop()
            return
        allowed = budget if budget > 1 else 1
        for san in opponent_choices(board, allowed):
            move = board.parse_san(san)
            board.push(move)
            walk(board, sans + [san], 1)     # branch once, then stay narrow
            board.pop()

    board = chess.Board()
    root = spec["root"].split()
    for san in root:
        board.push_san(san)
    walk(board, root, spec.get("branch", 1))

    # End every line on YOUR move: the last thing a drill shows should be a
    # question, not the opponent replying to your answer.
    trimmed = []
    for sans, tg in lines:
        while sans and ((len(sans) % 2 == 0) == (mine == chess.WHITE)):
            sans = sans[:-1]
        if len(sans) > len(spec["root"].split()):
            trimmed.append((sans, [t for t in tg if t]))
    return trimmed


def main():
    wanted = set(sys.argv[1:]) - {"--all"}
    with open(ANALYSIS, encoding="utf-8") as fh:
        games = json.load(fh)["games"]
    book = opponent_book(games)

    path = find_engine(conf.load().get("engine", {}).get("path"))
    if not path:
        print("Needs Stockfish.")
        raise SystemExit(1)

    with chess.engine.SimpleEngine.popen_uci(path) as eng:
        eng.configure({"Threads": 4, "Hash": 512})
        for spec in SPECS:
            if wanted and spec["id"] not in wanted:
                continue
            lines = derive(spec, eng, book)
            print(f'\n# ==== {spec["id"]}  ({spec["color"]}, after {spec["root"]}) ====')
            for sans, tg in lines:
                note = ("   # " + "; ".join(tg)) if tg else ""
                print(f'    "{" ".join(sans)}",{note}')


if __name__ == "__main__":
    main()
