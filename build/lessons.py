"""
Stage 3b: turn your mistakes into LESSONS instead of into repeats.

  python3 build/lessons.py            # print the lessons your games support

The problem this solves
-----------------------
The old pipeline took each blunder you played and made it a flashcard, then
handed those flashcards to the same spaced-repetition scheduler that drills
opening moves. That scheduler is built to show a card forever at growing
intervals, which is right for memorising a move order and wrong for a tactic.
Seeing "you hung the knight on f6 in that game" for the fifth time teaches
nothing: you remember the position, not the pattern. You end up practising
recall of twelve specific boards instead of the skill they have in common.

So this module does what a coach does with the same evidence. It reads every
mistake, works out WHY it happened rather than just tagging WHAT it was, groups
the mistakes by cause, and writes a lesson per cause:

  diagnosis   what you actually do wrong, with the count and the cost, and
              links to your own games as proof. Not "you are weak at pins" --
              "in 41 of these you lost the piece you had just moved."

  principle   the one idea that fixes the whole group.

  habit       a concrete question to ask yourself at the board. Deliberate
              practice needs a specific target, and "play better" is not one.

  ladder      four stages of increasing difficulty. Stage 1 is two positions
              from your own games (only two -- that is the whole point);
              stages 2-4 are FRESH puzzles on the same pattern, drawn from a
              pool so a review never repeats a position you have already
              solved. Difficulty steps up so you are always working just past
              what you can already do.

Why the grouping is greedy
--------------------------
One mistake can support several lessons -- a hung knight is also a fork and
also a loose piece. Ranking each lesson independently by total cost would
produce six lessons that are all secretly the same lesson. Instead we take the
lesson explaining the most centipawns, mark its mistakes as accounted for, and
re-rank the rest on what is LEFT. The result is a short list that between them
covers as much of your losses as possible, which is the list a coach would
actually give you.

Output is consumed by build_exercises.py, which fills in the puzzle pools.
"""

import collections
import json
import os

import chess

import themes as T
import weaknesses as W

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
ANALYSIS = os.path.join(ROOT, "data", "analysis.json")

# Motifs that mean "you missed a tactic" as opposed to "you had no plan".
TACTICAL = {"hangingPiece", "fork", "pin", "skewer", "discoveredAttack",
            "capturingDefender", "backRankMate", "trappedPiece",
            "mateIn1", "mateIn2", "mateIn3", "xRayAttack"}

# A lesson needs this much evidence before we will claim it about you. Below
# it we are pattern-matching on noise, and a confident wrong diagnosis is
# worse than no diagnosis.
MIN_EVIDENCE = 8

# How many of your own positions a lesson opens with. Deliberately tiny: their
# job is to prove the diagnosis is about YOU, then get out of the way.
OWN_POSITIONS = 2


# ---------------------------------------------------------------------------
# reading one mistake
# ---------------------------------------------------------------------------

def loose_pieces(board, color):
    """Your pieces with no defender. 'Loose pieces drop off' -- the single
    most useful thing an 800 can learn to count."""
    n = 0
    for sq in chess.SQUARES:
        pc = board.piece_at(sq)
        if not pc or pc.color != color:
            continue
        if pc.piece_type in (chess.PAWN, chess.KING):
            continue
        if not board.attackers(color, sq):
            n += 1
    return n


def facts(err, game):
    """Everything we can diagnose about one mistake, from the board itself."""
    f = {
        "cp_loss": err.get("cp_loss") or 0,
        "severity": err.get("severity"),
        "move_number": err.get("move_number") or 0,
        "themes": set(err.get("themes") or []),
        # "Winning" means clearly winning (+3), and "threw it" means the
        # position was no longer winning afterwards. A +2 that becomes +1.4 is
        # an inaccuracy in a good position, not a conversion failure.
        "threw_a_win": ((err.get("cp_best") or 0) >= 300
                        and (err.get("cp_played") or 0) <= 50),
        "clock_frac": None,
    }

    base = W.base_seconds(game.get("time_control"))
    if base and err.get("clock") is not None:
        f["clock_frac"] = max(0.0, min(1.0, err["clock"] / base))

    try:
        board = chess.Board(err["fen"])
        played = chess.Move.from_uci(err["played_uci"])
        best = chess.Move.from_uci(err["best_uci"])
    except (ValueError, KeyError):
        return f

    me = board.turn
    f["loose"] = loose_pieces(board, me)
    f["played_is_capture"] = board.is_capture(played)
    f["played_gives_check"] = board.gives_check(played)
    moved = board.piece_at(played.from_square)
    f["moved_piece"] = moved.piece_type if moved else None
    f["moved_queen_early"] = (f["moved_piece"] == chess.QUEEN
                              and f["move_number"] <= 10)

    # A capture that loses material on the exchange -- the automatic recapture.
    if f["played_is_capture"]:
        try:
            f["played_see"] = T.see(board, played)
        except Exception:
            f["played_see"] = None

    # Material the best move would have won and you did not take.
    f["best_is_capture"] = board.is_capture(best)
    if f["best_is_capture"]:
        try:
            f["best_see"] = T.see(board, best)
        except Exception:
            f["best_see"] = None
    f["declined_material"] = bool(f.get("best_see") and f["best_see"] >= 2
                                  and not f["played_is_capture"])

    # What the opponent wins in reply, and whether it is the piece you moved.
    after = board.copy(stack=False)
    after.push(played)
    ref = err.get("refutation_pv") or []
    if ref:
        try:
            rm = chess.Move.from_uci(ref[0])
            victim = after.piece_at(rm.to_square)
            f["ref_is_capture"] = victim is not None
            f["ref_victim"] = victim.piece_type if victim else None
            f["ref_target"] = rm.to_square
            f["lost_what_i_moved"] = (rm.to_square == played.to_square)
            f["ref_gives_check"] = after.gives_check(rm)
        except (ValueError, AssertionError):
            pass

    # Did their PREVIOUS move create the threat you then walked into? This is
    # the difference between "I miscalculated" and "I never looked at their
    # move at all", and they need different fixes.
    prev = err.get("prev_uci")
    if prev and f.get("ref_target") is not None:
        try:
            pm = chess.Move.from_uci(prev)
            f["threat_from_their_last_move"] = (
                pm.to_square == f["ref_target"]
                or f["ref_target"] in board.attacks(pm.to_square))
        except (ValueError, AssertionError):
            pass

    return f


# ---------------------------------------------------------------------------
# the lesson catalogue
# ---------------------------------------------------------------------------
# `when` reads the facts above. `themes` are Lichess puzzle tags used to build
# the drill pool. `rating_shift` nudges a lesson's ladder up or down when the
# pattern is inherently harder or easier than average.

CATALOGUE = [
    {
        "id": "moved-into-it",
        "title": "The piece you lose is the piece you just moved",
        "when": lambda f: f.get("lost_what_i_moved"),
        "principle":
            "You are choosing a move by what it does, and not checking what "
            "the destination square is worth. The square a piece lands on is "
            "part of the move.",
        "habit":
            "Before you let go: name every enemy piece that can reach the "
            "square you are moving to, and every piece of yours that defends "
            "it. If the first list is longer, find another move.",
        "themes": {"hangingPiece", "fork"},
    },
    {
        "id": "their-move-was-a-question",
        "title": "You answer their move without asking what it attacks",
        "when": lambda f: (f.get("threat_from_their_last_move")
                           and not f.get("lost_what_i_moved")),
        "principle":
            "You are playing your own plan while your opponent is making "
            "threats. Their last move is new information, every time.",
        "habit":
            "After their move, before anything else: what does the piece they "
            "just moved now attack? Say the squares out loud.",
        "themes": {"hangingPiece", "fork", "pin", "discoveredAttack"},
    },
    {
        "id": "loose-pieces",
        "title": "Loose pieces drop off",
        "when": lambda f: (f.get("loose", 0) >= 2 and f.get("ref_is_capture")),
        "principle":
            "A piece with no defender does not have to be attacked to be a "
            "problem -- it is the thing that makes forks, pins and skewers "
            "work. Two loose pieces is a tactic waiting for your opponent.",
        "habit":
            "Every move: count your pieces with no defender. More than one, "
            "and your first job is to fix that, not to attack.",
        "themes": {"hangingPiece", "fork", "skewer"},
    },
    {
        "id": "free-material-declined",
        "title": "Free material you walked past",
        "when": lambda f: f.get("declined_material"),
        "principle":
            "You are looking for a good move before checking whether a winning "
            "one is already on the board. Most games under 1200 are decided by "
            "someone leaving a piece out and the other player noticing.",
        "habit":
            "First question every single move: is anything of theirs "
            "undefended, or defended by less than what attacks it?",
        "themes": {"hangingPiece", "capturingDefender", "fork"},
    },
    {
        "id": "automatic-recapture",
        "title": "You capture because you can, not because it wins",
        "when": lambda f: (f.get("played_is_capture")
                           and f.get("played_see") is not None
                           and f["played_see"] < 0),
        "principle":
            "A capture feels safe because it is forcing, but an exchange you "
            "lose is just a slower way of giving material away.",
        "habit":
            "Before capturing, count the whole exchange: what recaptures, what "
            "recaptures that, and who is ahead when the square goes quiet.",
        "themes": {"capturingDefender", "hangingPiece"},
    },
    {
        "id": "knight-forks",
        "title": "You do not look at where knights can jump",
        "when": lambda f: "fork" in f["themes"],
        "principle":
            "Knights are the only piece that attacks squares it is not "
            "pointing at, which is exactly why beginners lose material to "
            "them. A knight two moves away is already a threat.",
        "habit":
            "Find every enemy knight. List the squares it can reach next move. "
            "Is anything of yours -- king included -- on two of them?",
        "themes": {"fork"},
    },
    {
        "id": "pins",
        "title": "Pinned pieces are not defenders",
        "when": lambda f: "pin" in f["themes"],
        "principle":
            "A pinned piece still looks like it is guarding a square, and it "
            "is not. Most of your pin losses are you relying on a defender "
            "that cannot legally move.",
        "habit":
            "When you count defenders of a square, check each one: if it "
            "moved, would something worse be exposed behind it?",
        "themes": {"pin"},
    },
    {
        "id": "skewers-and-discoveries",
        "title": "Pieces lined up on the same line",
        "when": lambda f: bool(f["themes"] & {"skewer", "discoveredAttack",
                                              "xRayAttack"}),
        "principle":
            "Two of your pieces on one rank, file or diagonal is a standing "
            "invitation -- one enemy move attacks both, or unmasks something "
            "behind.",
        "habit":
            "Scan the lines through your king and queen. Anything of yours "
            "sharing a line with them is a target.",
        "themes": {"skewer", "discoveredAttack"},
    },
    {
        "id": "threw-a-win",
        "title": "Winning positions you talk yourself out of",
        "when": lambda f: f.get("threw_a_win"),
        "principle":
            "When you are ahead, complications only help the player who is "
            "behind. Trading pieces reduces the number of ways you can lose, "
            "and every trade makes your extra material worth more.",
        "habit":
            "Ahead in material? Offer a trade whenever you can, avoid "
            "sharpening the position, and head for an endgame.",
        "themes": {"endgame", "advancedPawn", "queenEndgame", "rookEndgame"},
        "rating_shift": -100,
    },
    {
        "id": "back-rank",
        "title": "Your back rank",
        "when": lambda f: "backRankMate" in f["themes"],
        "principle":
            "Three pawns in front of a castled king is safe from everything "
            "except the rank behind it. This costs you more per occurrence "
            "than any other pattern, because it is usually mate.",
        "habit":
            "Once the queens or rooks are active: can anything of theirs get "
            "to my back rank, and does my king have a square?",
        "themes": {"backRankMate"},
    },
    {
        "id": "missed-mate",
        "title": "Mates you had and did not see",
        "when": lambda f: bool(f["themes"] & {"mateIn1", "mateIn2", "mateIn3"}),
        "principle":
            "Forced mate is the one calculation that ends the argument. "
            "Missing it is the most expensive kind of miss there is.",
        "habit":
            "Whenever their king has fewer than two escape squares, stop and "
            "check every check you have.",
        "themes": {"mateIn1", "mateIn2", "mateIn3"},
    },
    {
        "id": "trapped-and-sorties",
        "title": "Pieces that run out of squares",
        "when": lambda f: ("trappedPiece" in f["themes"]
                           or f.get("moved_queen_early")),
        "principle":
            "A piece deep in their position with no retreat is not attacking, "
            "it is hostage. This is what early queen and bishop raids cost.",
        "habit":
            "Before moving a piece past the middle of the board, count its "
            "escape squares. Fewer than two, and it needs a reason.",
        "themes": {"trappedPiece"},
    },
    {
        "id": "the-clock",
        "title": "The clock, not the chess",
        "when": lambda f: (f.get("clock_frac") is not None
                           and f["clock_frac"] < 0.15),
        "principle":
            "This is not a pattern you can drill away -- it is a time budget "
            "problem. Your blunder rate roughly doubles once the clock gets "
            "low, which means the same tactics you can solve on a puzzle "
            "screen are the ones you miss in a game.",
        "habit":
            "Spend your time in the first 15 moves, not the last 5. Under a "
            "minute: stop calculating, play the safe move, keep pieces "
            "defended. And play a slower time control -- it is worth more "
            "rating than any puzzle set.",
        "themes": {"mateIn1", "hangingPiece", "fork"},
        "rating_shift": -150,
        "note": "drills here are deliberately easy and fast -- the skill is "
                "recognition speed, not depth",
    },
    {
        "id": "leaving-the-opening",
        "title": "The move your opening ends",
        # No tactical motif fired: this is the move that does nothing, not a
        # tactic you missed. Those belong to the pattern lessons above.
        "when": lambda f: (10 <= f["move_number"] <= 20
                           and not (f["themes"] & TACTICAL)),
        "principle":
            "Your book runs out and you have no plan, so you make a move that "
            "does not do anything and the position turns. This is where the "
            "largest single share of your losses happens.",
        "habit":
            "The move your prep ends: stop and answer three questions. Which "
            "of my pieces is worst placed? Where does it belong? What is my "
            "opponent's plan?",
        "themes": {"middlegame", "hangingPiece", "fork", "pin"},
    },
]


# ---------------------------------------------------------------------------
# building the lesson list
# ---------------------------------------------------------------------------

def collect(data):
    """[(game, err, facts)] for every serious mistake of yours."""
    out = []
    for g in data["games"]:
        if not g.get("plies"):
            continue
        for e in g.get("errors") or []:
            if not e.get("is_mine"):
                continue
            if e.get("severity") not in ("mistake", "blunder"):
                continue
            out.append((g, e, facts(e, g)))
    return out


def build(data, limit=6):
    """Rank the catalogue against your games; return the lessons to teach.

    Greedy by unexplained cost -- see the module docstring for why that beats
    ranking each lesson on its own total.
    """
    rows = collect(data)
    if not rows:
        return []

    matches = {}
    for spec in CATALOGUE:
        hit = [i for i, (_g, _e, f) in enumerate(rows) if spec["when"](f)]
        if len(hit) >= MIN_EVIDENCE:
            matches[spec["id"]] = set(hit)

    total_cp = sum(r[1]["cp_loss"] for r in rows) or 1
    claimed = set()
    chosen = []

    while len(chosen) < limit:
        best_id, best_gain, best_new = None, 0, None
        for spec in CATALOGUE:
            idxs = matches.get(spec["id"])
            if not idxs or spec["id"] in {c["id"] for c in chosen}:
                continue
            fresh = idxs - claimed
            gain = sum(rows[i][1]["cp_loss"] for i in fresh)
            if gain > best_gain:
                best_id, best_gain, best_new = spec["id"], gain, fresh
        if not best_id or len(best_new) < MIN_EVIDENCE // 2:
            break

        spec = next(s for s in CATALOGUE if s["id"] == best_id)
        all_idxs = sorted(matches[best_id],
                          key=lambda i: -rows[i][1]["cp_loss"])
        claimed |= best_new

        # the two of your own positions the lesson opens with: biggest first,
        # but only ones that make a fair puzzle (one clearly best move)
        own = []
        for i in sorted(best_new, key=lambda i: -rows[i][1]["cp_loss"]) + all_idxs:
            g, e, _f = rows[i]
            if e.get("mate_available") or (e.get("second_gap") or 0) >= 100:
                own.append({
                    "gameId": g["id"], "ply": e["ply"],
                    "url": g.get("url"), "endTime": g.get("end_time"),
                    "moveNumber": e["move_number"], "played": e["played"],
                    "cpLoss": e["cp_loss"],
                })
            if len(own) >= OWN_POSITIONS:
                break

        # Show evidence this lesson is the BEST explanation for, not
        # positions an earlier lesson already accounted for -- otherwise the
        # same game link turns up under four different headings.
        distinct = sorted(best_new, key=lambda i: -rows[i][1]["cp_loss"])[:3]
        examples = [{
            "url": rows[i][0].get("url"),
            "moveNumber": rows[i][1]["move_number"],
            "played": rows[i][1]["played"],
            "best": rows[i][1]["best"],
            "cpLoss": rows[i][1]["cp_loss"],
        } for i in distinct]

        cp_all = sum(rows[i][1]["cp_loss"] for i in matches[best_id])
        chosen.append({
            "id": spec["id"],
            "title": spec["title"],
            "principle": spec["principle"],
            "habit": spec["habit"],
            "note": spec.get("note"),
            "themes": sorted(spec["themes"]),
            "ratingShift": spec.get("rating_shift", 0),
            "evidence": {
                "count": len(matches[best_id]),
                "cpLost": cp_all,
                "share": round(100.0 * cp_all / total_cp, 1),
                "newlyExplained": len(best_new),
                "examples": examples,
            },
            "ownPositions": own,
            "diagnosis": diagnose(spec, rows, matches[best_id]),
        })

    return chosen


def diagnose(spec, rows, idxs):
    """The sentence that tells you what you do, with your own numbers in it.

    Deliberately no total-centipawns figure. Evaluations are clamped at +/-10
    pawns before differencing, so a total reads "costing about 1170 pawns",
    which is not a quantity of anything -- it is 304 clamped differences added
    up. The average per mistake IS meaningful, and so is how many of them were
    bad enough to change the result.
    """
    n = len(idxs)
    cp = sum(rows[i][1]["cp_loss"] for i in idxs)
    avg = (cp / n) / 100 if n else 0
    blunders = sum(1 for i in idxs if rows[i][1]["severity"] == "blunder")
    games = len({rows[i][0]["id"] for i in idxs})

    detail = ""
    if spec["id"] == "moved-into-it":
        pieces = collections.Counter(
            rows[i][2].get("ref_victim") for i in idxs)
        names = {chess.KNIGHT: "knights", chess.BISHOP: "bishops",
                 chess.ROOK: "rooks", chess.QUEEN: "queens",
                 chess.PAWN: "pawns"}
        top = [(names.get(k), v) for k, v in pieces.most_common(2) if k]
        if top:
            detail = ("  Most often it is a " +
                      " then a ".join(t[0][:-1] for t in top if t[0]) + ".")
    elif spec["id"] == "loose-pieces":
        avg = sum(rows[i][2].get("loose", 0) for i in idxs) / max(n, 1)
        detail = f"  You averaged {avg:.1f} undefended pieces in those positions."
    elif spec["id"] == "the-clock":
        detail = ("  These are the ones where you had under 15% of your clock "
                  "left.")
    elif spec["id"] == "leaving-the-opening":
        mv = collections.Counter(rows[i][1]["move_number"] for i in idxs)
        peak = mv.most_common(1)[0][0]
        detail = f"  The single worst move number for you is {peak}."

    sev = (f", {blunders} of them badly enough to change the result"
           if 0 < blunders < n else "")
    return (f"{n} times across {games} games — about {avg:.1f} pawns "
            f"each time{sev}.{detail}")


def main():
    with open(ANALYSIS, encoding="utf-8") as fh:
        data = json.load(fh)
    for i, L in enumerate(build(data), 1):
        ev = L["evidence"]
        print(f"\n{i}. {L['title'].upper()}")
        print(f"   {L['diagnosis']}")
        print(f"   {ev['count']}x · {ev['share']}% of everything you lost "
              f"· {ev['newlyExplained']} not explained by an earlier lesson")
        print(f"   PRINCIPLE  {L['principle']}")
        print(f"   HABIT      {L['habit']}")
        print(f"   drills     {', '.join(L['themes'])}")
        for ex in ev["examples"][:2]:
            print(f"     e.g. move {ex['moveNumber']}: you played "
                  f"{ex['played']}, best was {ex['best']}  {ex['url']}")


if __name__ == "__main__":
    main()
