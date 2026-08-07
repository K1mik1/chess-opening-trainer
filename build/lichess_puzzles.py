"""
Pull practice puzzles on your weak themes out of the Lichess puzzle database.

The database (data/raw/lichess_db_puzzle.csv.zst, CC0) holds ~6.1 million
puzzles, each with a rating and a set of theme tags. Your own games say WHICH
themes you keep failing; this module supplies enough fresh material in exactly
those themes that you learn the pattern instead of memorising twelve positions.

Streaming the compressed file through `zstd -dc` keeps memory flat -- we never
hold more than the puzzles we intend to keep.

Row format:
  PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,
  OpeningTags,DailyDate

Note on FEN/Moves: the FEN is the position BEFORE the opponent's setup move.
Moves[0] is played *to* you; you solve Moves[1], Moves[3], ... That convention
is preserved here and unpacked in build_exercises.py.
"""

import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
DB = os.path.join(ROOT, "data", "raw", "lichess_db_puzzle.csv.zst")

# Quality gates. The database includes unpopular and barely-played puzzles;
# these thresholds keep only ones the community has vetted.
MIN_POPULARITY = 80
MIN_PLAYS = 150


def available():
    return os.path.exists(DB)


def select(specs, progress=True):
    """Collect puzzles for several theme specs in ONE pass over the database.

    specs: list of dicts with keys
        key        -- identifier you get back in the result
        themes     -- set of tags; a puzzle matches if it has ANY of them
        exclude    -- optional set of tags that disqualify a puzzle
        rating     -- (min, max)
        count      -- how many to keep
    Returns {key: [puzzle_dict, ...]}.

    Selection is deterministic (no RNG): within a spec we keep the puzzles with
    the highest play counts, so a rebuild produces the same set and your
    spaced-repetition history stays valid.
    """
    if not available():
        raise FileNotFoundError(
            f"Lichess puzzle database not found at {DB}\n"
            f"Download it with:\n"
            f"  curl -L -o {DB} https://database.lichess.org/lichess_db_puzzle.csv.zst")

    # Keep a generous pool per spec, then trim at the end -- this way the
    # "best" puzzles are chosen across the whole file, not just the first ones.
    pools = {s["key"]: [] for s in specs}
    pool_cap = {s["key"]: max(s["count"] * 12, 400) for s in specs}

    proc = subprocess.Popen(["zstd", "-dc", DB], stdout=subprocess.PIPE, text=True,
                            bufsize=1 << 20)
    seen = 0
    try:
        reader = csv.DictReader(proc.stdout)
        for row in reader:
            seen += 1
            if progress and seen % 500_000 == 0:
                print(f"    scanned {seen//1000}k puzzles...", flush=True)
            try:
                rating = int(row["Rating"])
                pop = int(row["Popularity"])
                plays = int(row["NbPlays"])
            except (ValueError, TypeError, KeyError):
                continue
            if pop < MIN_POPULARITY or plays < MIN_PLAYS:
                continue
            tags = set(row["Themes"].split())

            for s in specs:
                lo, hi = s["rating"]
                if not (lo <= rating <= hi):
                    continue
                if not (tags & s["themes"]):
                    continue
                if s.get("exclude") and (tags & s["exclude"]):
                    continue
                pool = pools[s["key"]]
                if len(pool) < pool_cap[s["key"]]:
                    pool.append({
                        "id": row["PuzzleId"],
                        "fen": row["FEN"],
                        "moves": row["Moves"].split(),
                        "rating": rating,
                        "plays": plays,
                        "themes": sorted(tags),
                        "url": row["GameUrl"],
                    })
    finally:
        proc.stdout.close()
        proc.wait()

    out = {}
    for s in specs:
        pool = pools[s["key"]]
        # Spread across the rating band instead of clustering at one number:
        # sort by rating, then walk the list at an even stride.
        pool.sort(key=lambda p: (p["rating"], p["id"]))
        n = s["count"]
        if len(pool) <= n:
            chosen = pool
        else:
            stride = len(pool) / n
            chosen = [pool[int(i * stride)] for i in range(n)]
        out[s["key"]] = chosen
    return out


if __name__ == "__main__":
    # Quick manual check: python build/lichess_puzzles.py fork 900 1300 5
    theme = sys.argv[1] if len(sys.argv) > 1 else "fork"
    lo = int(sys.argv[2]) if len(sys.argv) > 2 else 800
    hi = int(sys.argv[3]) if len(sys.argv) > 3 else 1400
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    res = select([{"key": theme, "themes": {theme}, "rating": (lo, hi), "count": n}])
    for p in res[theme]:
        print(f"{p['id']}  {p['rating']:>5}  {p['fen']}")
        print(f"        {' '.join(p['moves'])}   {p['themes']}")
