"""
Recompute tactical themes on an existing analysis, without the engine.

  python3 build/retag.py            # dry run: show what would change
  python3 build/retag.py --write    # rewrite analysis.json + the per-game cache

Why this exists
---------------
Theme detection (themes.py) is pure board geometry -- no search. So when a
detector is wrong, the fix does not need Stockfish to run again: everything
classify() wants is already in the cached record (the FEN, the move played,
the engine's best move, and the refutation line). Re-analysing 264 games to
change a heuristic would cost half an hour for no new information.

Mate themes are the exception, because they come from the engine's score
rather than the board, so mateIn1/2/3 and exposedKing are carried over from
the old record untouched.

This is a maintenance tool, not part of refresh.sh -- run it when a detector
changes. It bumps each record to the current SCHEMA so the next refresh does
not decide the cache is stale and redo the engine work anyway.
"""

import collections
import json
import os
import sys

import chess

import analyze_games as A
import themes as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
ANALYSIS = os.path.join(ROOT, "data", "analysis.json")
CACHE_DIR = os.path.join(ROOT, "data", "analysis")

# Engine-derived tags: keep whatever the original analysis decided.
ENGINE_TAGS = {"mateIn1", "mateIn2", "mateIn3", "exposedKing"}


def retag_error(err):
    """Return the new theme list for one error record, or None to leave it."""
    try:
        board = chess.Board(err["fen"])
        played = chess.Move.from_uci(err["played_uci"])
        best = chess.Move.from_uci(err["best_uci"]) if err.get("best_uci") else None
    except (ValueError, KeyError):
        return None
    if played not in board.legal_moves:
        return None

    pv = []
    for uci in err.get("refutation_pv") or []:
        try:
            pv.append(chess.Move.from_uci(uci))
        except ValueError:
            break

    tags = T.classify(board, played, best, pv=pv or None)
    tags |= (set(err.get("themes") or []) & ENGINE_TAGS)
    return sorted(tags)


def walk(games):
    before = collections.Counter()
    after = collections.Counter()
    touched = 0
    for g in games:
        for err in g.get("errors") or []:
            old = set(err.get("themes") or [])
            new = retag_error(err)
            if new is None:
                continue
            before.update(old)
            after.update(new)
            if set(new) != old:
                touched += 1
            err["themes"] = new
        g["schema"] = A.SCHEMA
    return before, after, touched


def main():
    write = "--write" in sys.argv
    with open(ANALYSIS, encoding="utf-8") as fh:
        data = json.load(fh)

    before, after, touched = walk(data["games"])

    keys = sorted(set(before) | set(after), key=lambda k: -before.get(k, 0))
    print(f"\n{touched} error records changed tags\n")
    print(f"  {'theme':<22} {'before':>8} {'after':>8}   {'change':>8}")
    for k in keys:
        b, a = before.get(k, 0), after.get(k, 0)
        if b == a:
            continue
        pct = f"{100*(a-b)/b:+.0f}%" if b else "new"
        print(f"  {k:<22} {b:>8} {a:>8}   {pct:>8}")

    if not write:
        print("\nDry run. Re-run with --write to save.")
        return

    with open(ANALYSIS, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"\nWrote {ANALYSIS}")

    # keep the per-game cache in step, or the next refresh re-analyses
    by_id = {g["id"]: g for g in data["games"]}
    n = 0
    for name in os.listdir(CACHE_DIR):
        if not name.endswith(".json"):
            continue
        path = os.path.join(CACHE_DIR, name)
        try:
            with open(path, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        fresh = by_id.get(rec.get("id"))
        if not fresh:
            continue
        rec["errors"] = fresh["errors"]
        rec["schema"] = A.SCHEMA
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, separators=(",", ":"))
        n += 1
    print(f"Updated {n} cached game records to schema {A.SCHEMA}")


if __name__ == "__main__":
    main()
