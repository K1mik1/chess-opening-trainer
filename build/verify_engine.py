"""
Stockfish verification for repertoire lines that ECO does not cover.

Why this exists
---------------
generate.py's normal rule is "every move must appear in the Lichess ECO
database, or the build aborts". That rule is what makes the repertoire
trustworthy, and it should stay the default.

But ECO is a database of *named theory*, and it is thinnest exactly where a
beginner bleeds rating: 2.Qh5, 2.Qf3, 3.d3, 1.e3 — junk openings nobody names
because no strong player plays them. You still have to meet them every week.
Refusing to teach an answer because ECO has not named the refutation is the
wrong trade.

So a course may set `"verify": "engine"`, and then the authority for that
course is Stockfish instead of ECO:

  * every USER move must be within `tolerance` centipawns of the engine's best
    move at `depth`, so we never teach a move that throws away material;
  * OPPONENT moves are only checked for legality — they are the bad moves you
    actually face, and their badness is the point.

Verdicts are cached in engine_verified.json, which IS tracked in git. A fresh
clone therefore inherits the verification without needing Stockfish installed;
the engine only runs for lines nobody has verified yet. Think of it as a
lockfile for "this move is sound".

The cache key is the position EPD plus the move, so it survives move-order
changes and line re-shuffling in repertoire.py.
"""

import json
import os

import chess

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "engine_verified.json")

# A user move may be this many centipawns worse than the engine's choice and
# still be taught. 40cp is about "a slightly less accurate but perfectly
# sound move" -- wide enough that we are not chasing engine noise, tight
# enough to exclude anything that actually drops material.
DEFAULT_TOLERANCE = 40
DEFAULT_DEPTH = 18


def _key(epd, uci, depth):
    return f"{epd}|{uci}|d{depth}"


def load_cache():
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("verdicts", {})
    except (OSError, ValueError):
        return {}


def save_cache(verdicts):
    payload = {
        "_comment": "Stockfish verdicts for engine-verified repertoire moves. "
                    "Tracked in git so a fresh clone needs no engine. "
                    "Regenerate with: python3 build/generate.py --reverify",
        "tolerance": DEFAULT_TOLERANCE,
        "verdicts": dict(sorted(verdicts.items())),
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=False)
        fh.write("\n")


class Verifier:
    """Checks user moves against Stockfish, memoised on disk.

    Opens the engine lazily: a build whose every move is already cached never
    starts Stockfish at all, which is the normal case after the first run.
    """

    def __init__(self, engine_path=None, depth=DEFAULT_DEPTH,
                 tolerance=DEFAULT_TOLERANCE, allow_engine=True):
        self.depth = depth
        self.tolerance = tolerance
        self.engine_path = engine_path
        self.allow_engine = allow_engine
        self.cache = load_cache()
        self.dirty = False
        self.misses = []          # moves we could not verify (no engine)
        self._engine = None

    # -- engine lifecycle ---------------------------------------------------

    def _engine_or_none(self):
        if self._engine is not None:
            return self._engine
        if not self.allow_engine or not self.engine_path:
            return None
        import chess.engine
        self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
        self._engine.configure({"Threads": 4, "Hash": 256})
        return self._engine

    def close(self):
        if self._engine is not None:
            self._engine.quit()
            self._engine = None
        if self.dirty:
            save_cache(self.cache)

    # -- the check ----------------------------------------------------------

    def check(self, board, move):
        """Return (ok, detail). `board` is the position BEFORE `move`.

        ok is None when we have no cached verdict and no engine to make one --
        the caller decides whether that is fatal.
        """
        epd = board.epd()
        uci = move.uci()
        hit = self.cache.get(_key(epd, uci, self.depth))
        if hit is not None:
            return hit["loss"] <= self.tolerance, hit

        eng = self._engine_or_none()
        if eng is None:
            self.misses.append((epd, board.san(move)))
            return None, None

        import chess.engine
        limit = chess.engine.Limit(depth=self.depth)
        # MultiPV 1 twice is cheaper than MultiPV 2 here: we need the value of
        # the best move and the value of OUR move, and the second is a
        # constrained search over a single root move.
        best = eng.analyse(board, limit)
        ours = eng.analyse(board, limit, root_moves=[move])

        def cp(info):
            # Score from the point of view of the side to move, mate scores
            # folded to a large finite value so arithmetic works.
            s = info["score"].pov(board.turn)
            return s.score(mate_score=10000)

        best_cp, our_cp = cp(best), cp(ours)
        loss = max(0, best_cp - our_cp)
        best_move = best["pv"][0] if best.get("pv") else None
        verdict = {
            "loss": loss,
            "best": board.san(best_move) if best_move else None,
            "played": board.san(move),
            "depth": self.depth,
        }
        self.cache[_key(epd, uci, self.depth)] = verdict
        self.dirty = True
        return loss <= self.tolerance, verdict
