"""
Build step: compile the repertoire into an offline move-tree for the app.

  python build/generate.py

What it does:
  1. Loads the Lichess ECO database (build/eco/*.tsv) and builds
        - a set of every book position (every prefix of every named line), and
        - a map from a move-sequence to its opening name.
  2. For each course in repertoire.py, replays every line with python-chess to
        - verify legality, and
        - verify the line is fully "in book" (the whole sequence is a prefix of
          some named ECO line).  If not, the build ABORTS -- so no unverified or
          invented moves can ever reach the app.
  3. Merges the lines of each course into a move-tree, recording for every move:
        FEN before, side to move, SAN, UCI, from/to squares, castle/ep flags,
        the opening name reached, and whether it is the user's move.
     Enforces that at every user-move position there is exactly ONE book move.
  4. Emits app/repertoire.js as `window.REPERTOIRE = [...]`  (a JS file, not
     JSON, so the app can load it via <script> and run from a file:// URL with
     no web server and no CORS problems).
"""

import csv
import json
import os
import sys

import chess

from repertoire import REPERTOIRE

HERE = os.path.dirname(os.path.abspath(__file__))
ECO_DIR = os.path.join(HERE, "eco")
OUT = os.path.join(HERE, os.pardir, "app", "repertoire.js")


# ----------------------------------------------------------------------------
# 1. Load the ECO database
# ----------------------------------------------------------------------------

def load_eco():
    """Return (book_epds, name_by_epd).

    Book membership is checked by POSITION, not by move order, so that
    transpositions (e.g. reaching the same Caro-Kann position via 3.Nc3 or
    3.Nd2) are correctly recognised as book.

    book_epds:    set of EPDs (position + side + castling + ep, no move clocks)
                  that occur anywhere in any named line, including every
                  intermediate position.
    name_by_epd:  EPD -> opening name, recorded at the FINAL position of each
                  named line. When several named lines end on the same
                  position, the most specific (longest) one wins.
    """
    book_epds = set()
    name_by_epd = {}
    name_len = {}  # epd -> pgn length of the line that named it

    for letter in "abcde":
        path = os.path.join(ECO_DIR, f"{letter}.tsv")
        with open(path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                sans = pgn_to_sans(row["pgn"])
                board = chess.Board()
                book_epds.add(board.epd())
                for san in sans:
                    board.push_san(san)
                    book_epds.add(board.epd())
                epd = board.epd()
                if len(sans) >= name_len.get(epd, -1):
                    name_by_epd[epd] = row["name"]
                    name_len[epd] = len(sans)
    return book_epds, name_by_epd


def pgn_to_sans(pgn):
    """'1. e4 e5 2. Nf3' -> ['e4', 'e5', 'Nf3']  (strip move numbers)."""
    out = []
    for tok in pgn.replace(".", ". ").split():
        if tok.endswith(".") and tok[:-1].isdigit():
            continue
        if tok.isdigit():
            continue
        out.append(tok)
    return out


# ----------------------------------------------------------------------------
# 2 + 3. Validate lines and build the tree for one course
# ----------------------------------------------------------------------------

def make_node(board, name):
    return {
        "fen": board.fen(),
        "turn": "w" if board.turn == chess.WHITE else "b",
        "name": name,
        "children": {},   # san -> edge
        "_seen_lines": 0,  # popularity within this course (mainline ordering)
    }


def build_course(course, book_epds, name_by_epd):
    color = chess.WHITE if course["color"] == "white" else chess.BLACK

    root = make_node(chess.Board(), "Starting position")
    errors = []

    for line in course["lines"]:
        sans = line.split()
        board = chess.Board()
        node = root
        played = []

        for san in sans:
            # ---- legality ----
            try:
                move = board.parse_san(san)
            except ValueError as exc:
                errors.append(f"  ILLEGAL move '{san}' after {' '.join(played)} "
                              f"({exc})")
                break

            mover_is_white = board.turn == chess.WHITE
            from_sq = chess.square_name(move.from_square)
            to_sq = chess.square_name(move.to_square)
            is_castle = board.is_castling(move)
            is_ep = board.is_en_passant(move)

            # rook hop for castling, so the app can animate it too
            rook = None
            if is_castle:
                rank = "1" if mover_is_white else "8"
                if chess.square_file(move.to_square) > 4:   # king side
                    rook = {"from": "h" + rank, "to": "f" + rank}
                else:                                        # queen side
                    rook = {"from": "a" + rank, "to": "d" + rank}

            board.push(move)
            played.append(san)

            # ---- book check (by position, so transpositions count) ----
            if board.epd() not in book_epds:
                errors.append(f"  NOT IN BOOK: {' '.join(played)}  "
                              f"(move '{san}' leaves known theory)")
                break

            mine = (mover_is_white == (color == chess.WHITE))
            name = name_by_epd.get(board.epd()) or node["name"]

            edge = node["children"].get(san)
            if edge is None:
                child = make_node(board, name)
                edge = {
                    "san": san,
                    "uci": move.uci(),
                    "from": from_sq,
                    "to": to_sq,
                    "mine": mine,
                    "castle": rook,
                    "ep": is_ep,
                    "node": child,
                }
                node["children"][san] = edge
            edge["node"]["_seen_lines"] += 1
            node = edge["node"]

    # ---- enforce: user-move positions must have exactly one book move ----
    def check_unique(node, path):
        # group children by whose move they are
        mine_moves = [e for e in node["children"].values() if e["mine"]]
        if len(mine_moves) > 1:
            errors.append(
                f"  AMBIGUOUS repertoire: after {' '.join(path) or '(start)'} "
                f"you have multiple book moves {[e['san'] for e in mine_moves]} "
                f"-- pick one.")
        for san, e in node["children"].items():
            check_unique(e["node"], path + [san])

    check_unique(root, [])
    return root, errors


# ----------------------------------------------------------------------------
# tree post-processing: stats + ordering
# ----------------------------------------------------------------------------

def finalize(node):
    """Order children mainline-first, count leaves/quiz-moves, strip helpers."""
    children = list(node["children"].values())
    # most-travelled (mainline) first
    children.sort(key=lambda e: -e["node"]["_seen_lines"])

    my_moves = 0
    leaves = 0
    out_children = []
    for e in children:
        child_my, child_leaves = finalize(e["node"])
        my_moves += child_my + (1 if e["mine"] else 0)
        leaves += child_leaves
        e["node"].pop("_seen_lines", None)
        e["node"].pop("children_dict", None)
        out_children.append(e)

    if not children:
        leaves = 1

    node["children"] = out_children
    node.pop("_seen_lines", None)
    return my_moves, leaves


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    book_epds, name_by_epd = load_eco()
    print(f"Loaded ECO database: {len(name_by_epd)} named positions, "
          f"{len(book_epds)} book positions.\n")

    courses = []
    any_error = False

    for course in REPERTOIRE:
        root, errors = build_course(course, book_epds, name_by_epd)
        if errors:
            any_error = True
            print(f"[FAIL] {course['name']}")
            for e in errors:
                print(e)
            print()
            continue

        my_moves, leaves = finalize(root)
        courses.append({
            "id": course["id"],
            "color": course["color"],
            "tier": course.get("tier", 1),
            "name": course["name"],
            "summary": course["summary"],
            "tree": root,
            "stats": {"variations": leaves, "quizMoves": my_moves},
        })
        print(f"[ OK ] {course['name']:<34} "
              f"{leaves:>3} variations, {my_moves:>3} moves to learn")

    if any_error:
        print("\nBuild aborted: fix the repertoire lines above. "
              "Nothing was written.")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = json.dumps(courses, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("// AUTO-GENERATED by build/generate.py -- do not edit by hand.\n")
        fh.write("// Every move here is verified against the Lichess ECO database.\n")
        fh.write("window.REPERTOIRE = ")
        fh.write(payload)
        fh.write(";\n")

    size_kb = os.path.getsize(OUT) / 1024
    total_quiz = sum(c["stats"]["quizMoves"] for c in courses)
    print(f"\nWrote {OUT}  ({size_kb:.1f} KB)")
    print(f"{len(courses)} courses, {total_quiz} total moves to memorize.")


if __name__ == "__main__":
    main()
