"""
Stage 1: download your games from chess.com.

  python build/fetch_games.py [--username NAME] [--months N]

chess.com's public API needs no login and no API key -- your finished games are
public data. We ask for the list of monthly archives, then pull each month.

Archives for PAST months never change, so they are cached in data/games/ and
skipped on later runs. Only the current month is re-fetched. That makes the
fortnightly refresh cheap (one or two HTTP requests) instead of re-downloading
your whole history every time.

Output: data/games/YYYY-MM.json  (raw archive as served, one file per month)
        data/games/index.json    (flat list of the games we care about)
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import conf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
GAMES_DIR = os.path.join(ROOT, "data", "games")

# chess.com blocks requests with a default/empty User-Agent at the CDN; their
# API docs ask for something identifiable. Set "contact" in your local config
# to put your own address in it.
UA = conf.user_agent()


def get_json(url, tries=4):
    """GET a JSON document, retrying on transient failures and rate limits."""
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            # 429 = rate limited, 5xx = their side; both are worth a retry
            if exc.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                wait = 2 ** attempt
                print(f"      HTTP {exc.code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < tries - 1:
                wait = 2 ** attempt
                print(f"      {exc}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise
    return None


def month_key(url):
    """'.../games/2025/03' -> '2025-03'"""
    parts = url.rstrip("/").split("/")
    return f"{parts[-2]}-{parts[-1]}"


def fetch(username, months_back, time_classes, rated_only):
    os.makedirs(GAMES_DIR, exist_ok=True)

    print(f"Fetching archives for '{username}' ...")
    listing = get_json(f"https://api.chess.com/pub/player/{username}/games/archives")
    if listing is None:
        print(f"\n[FAIL] chess.com has no player called '{username}'.\n"
              f"       Check the spelling at https://www.chess.com/member/{username}")
        sys.exit(1)

    archives = listing.get("archives", [])
    if not archives:
        print(f"[FAIL] '{username}' has no finished public games yet.")
        sys.exit(1)

    wanted = archives[-months_back:] if months_back > 0 else archives
    now = datetime.now(timezone.utc)
    current = f"{now.year:04d}-{now.month:02d}"

    print(f"{len(archives)} month(s) of history; taking the most recent "
          f"{len(wanted)}.\n")

    for url in wanted:
        key = month_key(url)
        path = os.path.join(GAMES_DIR, f"{key}.json")
        # Past months are immutable -> trust the cache. The current month is
        # still accumulating games, so always refresh it.
        if os.path.exists(path) and key != current:
            with open(path, encoding="utf-8") as fh:
                n = len(json.load(fh).get("games", []))
            print(f"  {key}  cached   ({n} games)")
            continue
        data = get_json(url) or {"games": []}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        tag = "refreshed" if key == current else "downloaded"
        print(f"  {key}  {tag} ({len(data.get('games', []))} games)")
        time.sleep(0.4)          # be a polite API citizen

    # ---- flatten every cached month into one filtered index ----
    index = []
    skipped = {"variant": 0, "unrated": 0, "time_class": 0, "no_pgn": 0}
    for name in sorted(os.listdir(GAMES_DIR)):
        if not name.endswith(".json") or name == "index.json":
            continue
        with open(os.path.join(GAMES_DIR, name), encoding="utf-8") as fh:
            for g in json.load(fh).get("games", []):
                # Only standard chess -- no chess960/bughouse/crazyhouse, whose
                # mistakes say nothing about your normal play.
                if g.get("rules") != "chess":
                    skipped["variant"] += 1
                    continue
                if rated_only and not g.get("rated"):
                    skipped["unrated"] += 1
                    continue
                if g.get("time_class") not in time_classes:
                    skipped["time_class"] += 1
                    continue
                if not g.get("pgn"):
                    skipped["no_pgn"] += 1        # ongoing / aborted games
                    continue

                white = g.get("white", {})
                black = g.get("black", {})
                me_is_white = white.get("username", "").lower() == username.lower()
                me, them = (white, black) if me_is_white else (black, white)

                index.append({
                    "id": g.get("uuid") or g.get("url"),
                    "url": g.get("url"),
                    "end_time": g.get("end_time"),
                    "time_class": g.get("time_class"),
                    "time_control": g.get("time_control"),
                    "color": "white" if me_is_white else "black",
                    "my_rating": me.get("rating"),
                    "opp_rating": them.get("rating"),
                    "opp_name": them.get("username"),
                    "result": me.get("result"),      # win / checkmated / resigned / ...
                    "eco": g.get("eco"),
                    "pgn": g.get("pgn"),
                })

    index.sort(key=lambda g: g.get("end_time") or 0)
    out = os.path.join(GAMES_DIR, "index.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"username": username, "games": index}, fh)

    # ---- report ----
    print(f"\n[ OK ] {len(index)} games ready for analysis.")
    if index:
        by_class = {}
        for g in index:
            by_class[g["time_class"]] = by_class.get(g["time_class"], 0) + 1
        print("       " + " · ".join(f"{k}: {v}" for k, v in
                                     sorted(by_class.items(), key=lambda x: -x[1])))
        first = datetime.fromtimestamp(index[0]["end_time"], timezone.utc)
        last = datetime.fromtimestamp(index[-1]["end_time"], timezone.utc)
        print(f"       {first:%d %b %Y} → {last:%d %b %Y}")
        rated = [g["my_rating"] for g in index[-30:] if g.get("my_rating")]
        if rated:
            print(f"       recent rating ≈ {sum(rated) // len(rated)}")
    dropped = ", ".join(f"{v} {k}" for k, v in skipped.items() if v)
    if dropped:
        print(f"       (skipped {dropped})")
    return index


def main():
    cfg = conf.load()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--username", default=cfg.get("username"))
    ap.add_argument("--months", type=int, default=cfg.get("months_back", 6))
    args = ap.parse_args()

    if not args.username:
        print("[FAIL] No chess.com username set.\n"
              "       Run:  python3 build/fetch_games.py --username YOUR_NAME\n"
              "       (or set it in build/coach_config.local.json)")
        sys.exit(2)

    # Persist a username given on the command line so later stages and the
    # scheduled refresh job pick it up without being told again. It goes in the
    # gitignored local config, never in the tracked one.
    if args.username != cfg.get("username"):
        conf.save_local({"username": args.username})
        print(f"Saved username '{args.username}' to "
              f"build/coach_config.local.json\n")

    fetch(args.username, args.months,
          set(cfg.get("time_classes", ["rapid"])), cfg.get("rated_only", True))


if __name__ == "__main__":
    main()
