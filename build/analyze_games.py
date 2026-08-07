"""
Stage 2: run Stockfish over your games and find every mistake.

  python build/analyze_games.py [--jobs N] [--max-games N]

Two passes, because a full deep search of every position would take hours:

  SCAN    every position in the game at a shallow depth. Cheap, and enough to
          spot where the evaluation swung.
  VERIFY  only the positions the scan flagged, at full depth with MultiPV, to
          confirm the mistake was real and to learn what the right move was
          and by how much it beat the alternatives.

The verify pass is what makes a position usable as a puzzle: a puzzle is only
fair if the best move is clearly better than the second best, otherwise you're
being asked to guess between two reasonable moves.

Results are cached per game in data/analysis/, so the fortnightly refresh only
analyses games it has never seen.

Output: data/analysis/<game_id>.json  (one per game)
        data/analysis.json            (everything merged)
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time

import chess
import chess.engine
import chess.pgn

import conf
import themes as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
GAMES_INDEX = os.path.join(ROOT, "data", "games", "index.json")
ANALYSIS_DIR = os.path.join(ROOT, "data", "analysis")
MERGED = os.path.join(ROOT, "data", "analysis.json")

CLK_RE = re.compile(r"\[%clk\s+(\d+):(\d+):([\d.]+)\]")

# Bump when the per-game record gains or changes fields. Cached analyses with
# an older schema are recomputed rather than silently used with fields missing.
SCHEMA = 3


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def find_engine(path_setting):
    if path_setting and path_setting != "auto" and os.path.exists(path_setting):
        return path_setting
    for candidate in ("/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish",
                      "/usr/bin/stockfish", "stockfish"):
        found = candidate if os.path.exists(candidate) else None
        if found:
            return found
    from shutil import which
    return which("stockfish")


def cp_of(score, pov, clamp):
    """PovScore -> centipawns for `pov`, clamped, plus mate-in-N if any.

    Clamping matters: without it, going from +900 to +600 looks like a huge
    error when in reality both positions are completely winning. We only care
    about mistakes that change the outcome.
    """
    rel = score.pov(pov)
    mate = rel.mate()
    if mate is not None:
        cp = clamp if mate > 0 else -clamp
        return cp, mate
    cp = rel.score()
    if cp is None:
        return 0, None
    return max(-clamp, min(clamp, cp)), None


def parse_clocks(game):
    """Seconds remaining after each ply, from chess.com's [%clk] comments."""
    out = []
    node = game
    while node.variations:
        node = node.variation(0)
        m = CLK_RE.search(node.comment or "")
        if m:
            h, mnt, s = m.groups()
            out.append(int(h) * 3600 + int(mnt) * 60 + float(s))
        else:
            out.append(None)
    return out


# ---------------------------------------------------------------------------
# per-game analysis (runs inside a worker process)
# ---------------------------------------------------------------------------

def analyze_one(task):
    """Analyse one game, in its own process, with its own engine.

    The engine is opened and closed inside this call rather than being kept
    alive for the worker's lifetime. Starting Stockfish costs a few tens of
    milliseconds against ~15 seconds of analysis, so the overhead is noise --
    and in exchange there is no long-lived subprocess to leak, no global state
    across tasks, and no shutdown race where a worker cannot exit because its
    engine's reader thread is still attached.
    """
    meta, cfg = task
    cache = os.path.join(ANALYSIS_DIR, f"{_safe_id(meta['id'])}.json")
    if os.path.exists(cache):
        try:
            with open(cache, encoding="utf-8") as fh:
                cached = json.load(fh)
            if cached.get("schema") == SCHEMA:
                return cached
        except Exception:
            pass                        # corrupt or outdated cache -> redo it

    path = find_engine(cfg["engine"].get("path"))
    with chess.engine.SimpleEngine.popen_uci(path) as eng:
        eng.configure({"Threads": 1, "Hash": max(64, cfg["engine"].get("hash_mb", 512) // 4)})
        return _analyze(eng, meta, cfg)


def _analyze(eng, meta, cfg):
    ecfg, th = cfg["engine"], cfg["thresholds"]
    clamp = th.get("clamp", 1000)

    import io
    game = chess.pgn.read_game(io.StringIO(meta["pgn"]))
    if game is None:
        return None

    my_color = chess.WHITE if meta["color"] == "white" else chess.BLACK
    clocks = parse_clocks(game)

    # ---- collect the move list ----
    positions, moves = [], []
    board = game.board()
    for mv in game.mainline_moves():
        positions.append(board.fen())
        moves.append(mv)
        board.push(mv)
    positions.append(board.fen())                   # final position
    if len(moves) < 8:
        return _empty_record(meta)                  # too short to learn from

    # ---- PASS 1: shallow scan of every position ----
    # A node budget rather than a depth keeps per-position cost predictable:
    # depth 12 is instant in a quiet endgame and slow in a sharp middlegame,
    # which is exactly backwards from what we want when scanning hundreds of
    # games. Recall matters more than precision here -- the verify pass throws
    # out anything the scan over-flagged.
    scan_limit = chess.engine.Limit(nodes=ecfg.get("scan_nodes", 150_000),
                                    depth=ecfg.get("scan_depth", 12), time=0.30)
    evals = []                                      # cp from WHITE's point of view
    mates = []
    for fen in positions:
        b = chess.Board(fen)
        if b.is_game_over():
            # Terminal: score it directly rather than asking the engine.
            if b.is_checkmate():
                evals.append(-clamp if b.turn == chess.WHITE else clamp)
            else:
                evals.append(0)
            mates.append(None)
            continue
        info = eng.analyse(b, scan_limit)
        cp, mate = cp_of(info["score"], chess.WHITE, clamp)
        evals.append(cp)
        mates.append(mate)

    # ---- find candidate errors ----
    # Verification is by far the most expensive thing here (two deep searches
    # per candidate), so be deliberate about what earns one. Nothing
    # downstream consumes inaccuracies -- both the weakness ranking and the
    # puzzle selection require a mistake or a blunder -- so gating on a
    # scan-loss well above the inaccuracy line removes roughly half the work
    # without losing a single exercise. The gate sits below the mistake
    # threshold because the shallow scan is only approximate, leaving room for
    # the deep search to promote a borderline move.
    gate = max(th["inaccuracy"], th.get("verify_min_loss", 100))
    candidates = []
    for i, mv in enumerate(moves):
        b = chess.Board(positions[i])
        mover = b.turn
        sign = 1 if mover == chess.WHITE else -1
        loss = (sign * evals[i]) - (sign * evals[i + 1])
        if loss >= gate:
            candidates.append((i, loss, mover))

    # A collapse can flag dozens of moves in one lost game; the worst handful
    # already tell us everything that game has to teach.
    cap = th.get("max_verify_per_game", 20)
    if len(candidates) > cap:
        candidates = sorted(candidates, key=lambda c: -c[1])[:cap]
        candidates.sort(key=lambda c: c[0])       # back into move order

    # ---- PASS 2: verify the flagged ones properly ----
    verify_limit = chess.engine.Limit(depth=ecfg.get("verify_depth", 20),
                                      nodes=ecfg.get("verify_nodes", 1_200_000),
                                      time=2.0)
    multipv = ecfg.get("multipv", 3)
    errors = []
    for i, _rough_loss, mover in candidates:
        b = chess.Board(positions[i])
        try:
            infos = eng.analyse(b, verify_limit, multipv=multipv)
        except chess.engine.EngineError:
            continue
        if not infos:
            continue
        best_info = infos[0]
        best_cp, best_mate = cp_of(best_info["score"], mover, clamp)
        best_pv = best_info.get("pv") or []
        if not best_pv:
            continue
        best_move = best_pv[0]

        # eval after the move actually played, at the same depth
        after_b = chess.Board(positions[i])
        after_b.push(moves[i])
        if after_b.is_game_over():
            if after_b.is_checkmate():
                played_cp, played_mate = -clamp, -1
            else:
                played_cp, played_mate = 0, None
            played_pv = []
        else:
            pinfo = eng.analyse(after_b, verify_limit)
            played_cp, played_mate = cp_of(pinfo["score"], mover, clamp)
            played_pv = pinfo.get("pv") or []

        loss = best_cp - played_cp
        if loss < th["inaccuracy"]:
            continue                                # the scan was wrong; drop it

        severity = ("blunder" if loss >= th["blunder"]
                    else "mistake" if loss >= th["mistake"]
                    else "inaccuracy")

        # How much better is the best move than the runner-up? A big gap means
        # the position has one clear answer -- the mark of a fair puzzle.
        if len(infos) > 1:
            second_cp, _ = cp_of(infos[1]["score"], mover, clamp)
            gap = best_cp - second_cp
        else:
            gap = clamp

        tags = T.classify(b, moves[i], best_move,
                          mate_before=best_mate, mate_after=played_mate,
                          pv=played_pv)

        errors.append({
            "ply": i,
            "move_number": i // 2 + 1,
            "mover": "white" if mover == chess.WHITE else "black",
            "is_mine": mover == my_color,
            "fen": positions[i],
            # The opponent's previous move, so a puzzle can animate its way
            # into the position instead of dropping you into a cold FEN --
            # seeing what just changed is half of finding the answer.
            "prev_fen": positions[i - 1] if i > 0 else None,
            "prev_uci": moves[i - 1].uci() if i > 0 else None,
            "played": b.san(moves[i]),
            "played_uci": moves[i].uci(),
            "best": b.san(best_move),
            "best_uci": best_move.uci(),
            "pv": [m.uci() for m in best_pv[:8]],
            # How the opponent should have refuted the move actually played.
            # Drives the "what did that allow?" exercises.
            "refutation_pv": [m.uci() for m in played_pv[:6]],
            "cp_best": best_cp,
            "cp_played": played_cp,
            "cp_loss": loss,
            "second_gap": gap,
            "mate_available": best_mate,
            "severity": severity,
            "themes": sorted(tags),
            "clock": clocks[i] if i < len(clocks) else None,
        })

    # ---- per-game aggregates ----
    my_losses = []
    for i, mv in enumerate(moves):
        b = chess.Board(positions[i])
        if b.turn != my_color:
            continue
        sign = 1 if my_color == chess.WHITE else -1
        my_losses.append(max(0, (sign * evals[i]) - (sign * evals[i + 1])))

    record = {
        "schema": SCHEMA,
        "id": meta["id"], "url": meta["url"], "end_time": meta["end_time"],
        "time_class": meta["time_class"], "time_control": meta["time_control"],
        "color": meta["color"], "result": meta["result"],
        "my_rating": meta["my_rating"], "opp_rating": meta["opp_rating"],
        "eco": meta.get("eco"),
        "plies": len(moves),
        "acpl": round(sum(my_losses) / len(my_losses), 1) if my_losses else 0,
        "errors": errors,
        "opening_sans": [chess.Board(positions[k]).san(moves[k])
                         for k in range(min(16, len(moves)))],
    }
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    cache = os.path.join(ANALYSIS_DIR, f"{_safe_id(meta['id'])}.json")
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    return record


def _safe_id(gid):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(gid))[-80:]


def _empty_record(meta):
    return {"schema": SCHEMA, "id": meta["id"], "url": meta["url"], "end_time": meta["end_time"],
            "time_class": meta["time_class"], "time_control": meta.get("time_control"),
            "color": meta["color"], "result": meta["result"],
            "my_rating": meta.get("my_rating"), "opp_rating": meta.get("opp_rating"),
            "eco": meta.get("eco"), "plies": 0, "acpl": 0, "errors": [],
            "opening_sans": []}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    cfg = conf.load()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--max-games", type=int, default=cfg.get("max_games", 400))
    args = ap.parse_args()

    if not find_engine(cfg["engine"].get("path")):
        print("[FAIL] Stockfish not found. Install it with:  brew install stockfish")
        sys.exit(1)

    if not os.path.exists(GAMES_INDEX):
        print("[FAIL] No games yet. Run:  python build/fetch_games.py")
        sys.exit(1)

    with open(GAMES_INDEX, encoding="utf-8") as fh:
        index = json.load(fh)
    games = index["games"][-args.max_games:]

    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    def _needs_work(g):
        path = os.path.join(ANALYSIS_DIR, f"{_safe_id(g['id'])}.json")
        if not os.path.exists(path):
            return True
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh).get("schema") != SCHEMA
        except Exception:
            return True

    todo = [g for g in games if _needs_work(g)]

    print(f"{len(games)} games in scope · {len(todo)} need analysis "
          f"({len(games) - len(todo)} cached)")
    if todo:
        print(f"Running Stockfish on {args.jobs} workers "
              f"(scan d{cfg['engine']['scan_depth']} → verify d{cfg['engine']['verify_depth']})\n")
        start = time.time()
        done = 0
        tasks = [(g, cfg) for g in todo]
        with cf.ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for _rec in pool.map(analyze_one, tasks):
                done += 1
                elapsed = time.time() - start
                rate = done / elapsed if elapsed else 0
                eta = (len(todo) - done) / rate if rate else 0
                print(f"\r  analysed {done}/{len(todo)}  "
                      f"({rate*60:.0f} games/min, ~{eta/60:.1f} min left)   ",
                      end="", flush=True)
        print(f"\n  finished in {(time.time()-start)/60:.1f} min")

    # ---- merge every cached record for the games in scope ----
    merged = []
    for g in games:
        path = os.path.join(ANALYSIS_DIR, f"{_safe_id(g['id'])}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                rec = json.load(fh)
            if rec.get("schema") == SCHEMA:
                merged.append(rec)
    merged.sort(key=lambda r: r.get("end_time") or 0)
    with open(MERGED, "w", encoding="utf-8") as fh:
        json.dump({"username": index["username"], "games": merged}, fh)

    n_err = sum(len(r["errors"]) for r in merged)
    n_mine = sum(1 for r in merged for e in r["errors"] if e["is_mine"])
    n_blunder = sum(1 for r in merged for e in r["errors"]
                    if e["is_mine"] and e["severity"] == "blunder")
    acpls = [r["acpl"] for r in merged if r["plies"]]
    print(f"\n[ OK ] {len(merged)} games · {n_err} flagged positions "
          f"({n_mine} yours, {n_blunder} of them blunders)")
    if acpls:
        print(f"       your average centipawn loss: {sum(acpls)/len(acpls):.0f}")
    print(f"       wrote {MERGED}")


if __name__ == "__main__":
    main()
