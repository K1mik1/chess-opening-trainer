"""
Configuration loading, shared by every stage of the coach pipeline.

Settings live in two files:

  build/coach_config.json         tracked in git -- the defaults everyone gets
  build/coach_config.local.json   gitignored    -- YOUR username and overrides

The local file wins, key by key (nested dicts merge rather than replace). This
split matters for a repository other people clone:

  * your chess.com username never lands in a commit,
  * `git pull` brings in improved defaults without clobbering your settings,
  * and a fresh clone starts with a sensible config rather than someone else's.

Nothing needs the local file to exist -- without it you get the defaults, and
the only missing piece is the username.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS_PATH = os.path.join(HERE, "coach_config.json")
LOCAL_PATH = os.path.join(HERE, "coach_config.local.json")


def _merge(base, over):
    """Recursive dict merge; `over` wins at the leaves."""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    with open(DEFAULTS_PATH, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if os.path.exists(LOCAL_PATH):
        try:
            with open(LOCAL_PATH, encoding="utf-8") as fh:
                cfg = _merge(cfg, json.load(fh))
        except (OSError, ValueError) as exc:
            print(f"[warn] ignoring {LOCAL_PATH}: {exc}")
    return cfg


def save_local(updates):
    """Merge `updates` into the local override file, creating it if needed."""
    current = {}
    if os.path.exists(LOCAL_PATH):
        try:
            with open(LOCAL_PATH, encoding="utf-8") as fh:
                current = json.load(fh)
        except (OSError, ValueError):
            current = {}
    merged = _merge(current, updates)
    with open(LOCAL_PATH, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
        fh.write("\n")
    return merged


def username(cfg=None):
    cfg = cfg or load()
    return (cfg.get("username") or "").strip()


def user_agent(cfg=None):
    """The User-Agent chess.com sees.

    Their CDN rejects requests with a default or empty agent, and their API
    docs ask for something identifiable. `contact` is optional -- set it in
    your local config if you want your own address in there instead.
    """
    cfg = cfg or load()
    contact = (cfg.get("contact") or "").strip()
    base = "chess-opening-trainer/1.0 (personal training tool; " \
           "+https://github.com/lichess-org/chess-openings)"
    if contact:
        base = f"chess-opening-trainer/1.0 (personal training tool; {contact})"
    return base
