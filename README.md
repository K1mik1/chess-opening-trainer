# ♞ Chess Trainer

A small, offline, gamified chess trainer with two halves:

1. **An opening trainer** — memorize a focused repertoire of real book moves,
   with spaced repetition.
2. **A personal coach** — Stockfish reads your actual chess.com games, works out
   what you keep getting wrong, and builds tactics, calculation and endgame
   exercises aimed at exactly that.

Both run in one browser page, offline, with no server and no build step. The
target is **5–10 minutes a day** for a beginner-to-intermediate player.

---

## Quick start

```bash
git clone <this repo> && cd chess-opening-trainer

# macOS
brew install stockfish zstd && pip3 install chess

# Debian/Ubuntu
sudo apt install stockfish zstd python3-pip && pip3 install chess

./setup.sh          # asks for your chess.com username, then builds everything
```

Then open **`app/index.html`** in your browser.

`setup.sh` checks your dependencies, downloads the Lichess puzzle database,
analyses your games and offers to schedule a refresh every two weeks. The first
analysis takes 15-30 minutes for a few hundred games (250 blitz games on an
8-core M-series Mac took 16); every run after that only looks at games it has
not seen, so it finishes in a couple of minutes.

**Just want the opening trainer?** Skip `setup.sh` entirely and open
`app/index.html`. The coach is optional — the app works without it.

> Your chess.com username lives in `build/coach_config.local.json`, which is
> gitignored. Nothing personal is committed if you fork this.

---

## The opening trainer

You play your openings move by move; the app plays the opponent's book replies
and tells you **right or wrong** for each of your moves. A spaced-repetition
scheduler decides what to review each day so the moves stick **by heart**.

Every move in the app is a real **book move taken from the Lichess ECO
opening database** (`lichess-org/chess-openings`) — not invented. The build
step replays each line and *fails loudly* if any move isn't in the database.

---

## How to run it

No installation, no internet, no server.

1. Open the **`app`** folder.
2. Double-click **`index.html`** (it opens in your browser — Chrome, Edge, or
   Firefox).
3. That's it. Your progress saves automatically in the browser.

> Tip: bookmark the page, or right-click `index.html` → *Open with* → your
> browser, so it's one click each morning.

> Your progress lives in that browser's local storage on this PC. Use the same
> browser each day. (Don't open it in "private/incognito" mode — progress won't
> be saved.)

---

## The daily routine (your 5–10 minutes)

1. Open the app → press **▶ Start today's training**.
2. The app gives you the lines that are **due for review** plus a few **new
   lines** (default 4/day — change it at the bottom of the home screen).
3. For each line: make your move on the board (click the piece, then the
   destination square). ✓ = correct, ✗ = try again. The opponent's replies
   play themselves.
4. Forgot one? Use **💡 Hint** or **"I forgot — show me"**.
5. Finish the short session, keep your 🔥 streak alive, come back tomorrow.

The scheduler shows each line again at growing intervals (1 day → 3 → a week →
weeks) when you get it right, and brings it back fast when you slip. A line is
counted **"mastered"** once it survives to a 3-week interval; the **Mastery %**
and ★ ratings climb gradually as you learn and strengthen each line, so progress
shows from your very first session.

**Missed a few days?** No problem — reviews won't pile into an overwhelming wall.
The app caps how many reviews land on any single day (**Reviews per day**,
adjustable at the bottom of the home screen) and spreads any backlog across the
following days, most-fragile-lines-first. Nothing is skipped; the load just
smooths out so picking it back up stays a quick 5–10 minutes.

---

## The default repertoire

The repertoire that ships here is one example, aimed at a sub-1200 player who
wants a complete, low-theory answer to everything they will actually meet. It is
**not** meant to be the repertoire — see *[Make it yours](#make-it-yours)* to
swap in your own lines.

**12 courses · 41 variations · 192 book moves to memorize.** Each course has a
main line plus its most-played sidelines, and is tagged with a difficulty tier
that drives the learning curve (you learn the foundations first — see below).

**Tier 1 — Beginner (learn these first):**
| Course | You play | Against |
|--------|----------|---------|
| **Italian Game** (Giuoco Pianissimo) | White | 1…e5 |
| **Scotch Game** | White | 1…e5 |
| **Vienna Game** (incl. Frankenstein-Dracula) | White | 1…e5 |
| **Scandinavian** | White | 1…d5 |
| **London System** | White | 1.d4 (vs anything) |
| **Queen's Gambit** (QGD / QGA / Slav) | White | 1…d5 |

**Tier 2 — Intermediate:**
| Course | You play | Against |
|--------|----------|---------|
| **Ruy Lopez** (Closed / Open / Berlin) | White | 1…e5 |
| **Alapin** (2.c3) | White | 1…c5 |
| **French, Advance** (3.e5) | White | 1…e6 |
| **Caro-Kann** (Classical / Advance / Exchange / Panov) | Black | 1.e4 |
| **Petrov** (Classical / Cochrane / Modern / Four Knights) | Black | 1.e4 |
| **Slav** (main / Exchange / Quiet) | Black | 1.d4 |

You now have multiple weapons for the same situation (e.g. Italian, Scotch,
Vienna, and Ruy Lopez all answer 1…e5; London and Queen's Gambit are two 1.d4
systems; Caro-Kann and Petrov both answer 1.e4) — so you can rotate openings day
to day and learn the main lines of all the openings you'll actually meet under
1200.

### The learning curve
Courses are ordered Beginner → Intermediate. The daily scheduler introduces new
lines **from the top of that order**, so you master the simple, systematic
openings before the theory-heavy ones. The home screen shows which opening is
"next up", and you can always jump ahead by drilling any course directly.

---

## How it works (for the curious / to extend it)

```
chess-opening-trainer/
├── setup.sh              ← one-command setup for a fresh clone
├── app/                  ← THE APP (open index.html; nothing else needed)
│   ├── index.html
│   ├── style.css
│   ├── app.js            ← board, trainer engine, spaced repetition, gamification
│   ├── coach.js          ← puzzle model, adaptive difficulty, weakness report
│   ├── repertoire.js     ← generated opening tree (DB-verified). Not hand-edited.
│   └── exercises.js      ← generated from your games. Absent until you build it.
└── build/
    ├── eco/*.tsv         ← the Lichess ECO opening database (source of truth)
    ├── repertoire.py     ← the repertoire definition (edit this to change lines)
    ├── generate.py       ← compiles + verifies repertoire.py → app/repertoire.js
    ├── probe.py          ← asks the DB "what are the book replies after <line>?"
    │
    ├── conf.py           ← config loading (tracked defaults + local overrides)
    ├── fetch_games.py    ← 1. chess.com → data/games/          (incremental)
    ├── analyze_games.py  ← 2. Stockfish, two passes            (cached per game)
    ├── themes.py         ←    tactical motif detection (SEE, forks, pins, …)
    ├── weaknesses.py     ← 3. analysis → your weakness profile
    ├── lichess_puzzles.py←    filters the puzzle DB by theme + rating
    ├── build_exercises.py← 4. profile → app/exercises.js
    ├── refresh.sh        ←    runs 1–4; safe to re-run any time
    ├── get_puzzle_db.sh  ←    downloads the Lichess puzzle database
    ├── install_schedule.sh ←  the fortnightly launchd/cron job
    └── test_*.js|py      ←    the test suites
```

The app needs **no chess engine at runtime**: the build precomputes the board
position (FEN), the piece's from/to squares, and the opening name for every
move. At runtime a move is simply "correct" if it matches the precomputed one,
which is why both openings and tactics run from a `file://` URL with no server.

A **tactics puzzle and an opening line are the same object** — a start position
plus a list of move-edges — so one trainer engine plays both.

---

## Gamification

- **XP** for every correct move (+ bonus for a flawless line), **levels**, and a
  daily **🔥 streak**.
- **Mastery %** and ★ ratings per opening (graduated — they grow as you learn a
  line and strengthen with each successful review); an overall mastery ring on
  the home screen.
- **Badges**: first session, 7- and 30-day streaks, 100 moves, a flawless
  session, mastering an opening, and more.
- Little touches: move sounds, confetti on perfect lines and level-ups (toggle
  sound with 🔊 in the top bar).
- **Board themes** (pick at the bottom of the home screen): *Tournament Green*
  (chess.com style, default), *Walnut Parlor* (warm wooden board), and
  *Tournament Hall* (cool blue). All use a classic Staunton-style piece set and
  a traditional game-room look.

---

# 🎯 The personal coach (tactics from your real games)

The opening trainer above teaches you moves. This part works out **why you
actually lose games** — by reading your real chess.com history — and builds the
exercises to fix it.

Nothing here is hand-written advice: Stockfish analyses every move you played,
and the practice set is assembled from what it finds.

`./setup.sh` sets all of this up (see [Quick start](#quick-start)). You do
**not** need to download anything from chess.com by hand, and there is no login
or API key — finished games are public data.

## Keeping it current automatically

```bash
./build/install_schedule.sh            # refresh on the 1st and 15th, 03:30
./build/install_schedule.sh --status   # is it running? when did it last run?
./build/install_schedule.sh --remove   # stop
```

A plain `launchd` job on macOS, a crontab entry elsewhere — no Claude, no
subscription, no network service. It re-reads your recent games, re-diagnoses
your weaknesses, and rebuilds the exercises around whatever you are getting
wrong *lately*.

Two things make it safe to leave unattended: if a refresh fails (offline,
engine missing) your existing exercises are left exactly as they were, and
because analysis is cached per game it only ever looks at games it has not seen.
You can also just run `./build/refresh.sh` yourself whenever you like.

## What it builds

| Pack | What it trains |
|------|----------------|
| **Your own blunders** | The exact positions where you went wrong. "You played Rd1 here and it threw the game away — find what you missed." |
| **Punish the mistake** | Positions where your opponent blundered and you let them off. |
| **What did that allow?** | The position *after* your blunder, played from the other side. Training the refutation is how you learn to see it coming. |
| **Calculation ladder** | Multi-move forcing lines solved **blind** — the board does not move until you have entered the whole sequence, then it replays your line. This trains calculation depth, not pattern recall. |
| **Themed drills** | Fresh Lichess puzzles on your *measured* top weaknesses, at your level, so you meet each pattern often enough to internalise it. |
| **Endgame technique** | Converting won positions and holding difficult ones. |

Puzzles share the opening trainer's spaced-repetition scheduler, XP and streak,
and ride along in the same daily session — so the routine stays one 10-minute
sitting, now roughly half openings and half tactics (adjust at the bottom of the
home screen).

Difficulty is **adaptive**: puzzles are bundled across a wide rating band and the
app maintains your puzzle rating with an Elo update on every solve, so the level
self-corrects between rebuilds.

## The weakness report

Tap **"see the full report ›"** on the home screen for what the engine found:
where your points actually go (ranked by centipawns thrown away, not raw
frequency), which phase of the game you go wrong in, whether your blunders
cluster when the clock is low, how often you convert your opponents' mistakes,
and which openings you genuinely face. A plain-text copy lands in
`data/report.txt` after every refresh.

## How the pipeline works

*(File layout is in [How it works](#how-it-works-for-the-curious--to-extend-it) above.)*

Analysis is deliberately two-pass: a cheap **scan** of every position on a node
budget to find where the evaluation swung, then a deep **verify** with MultiPV
only on the flagged ones. The verify pass is what makes a position usable as a
puzzle — a position only becomes an exercise if the best move is clearly better
than the second best, so you are never asked to guess between two reasonable
moves and told you were wrong.

Verification is also *gated*: only moves the scan already thinks lost ~1 pawn
earn a deep search, and no more than 20 per game. Nothing downstream consumes
inaccuracies — both the weakness ranking and the puzzle selection require a
mistake or a blunder — so this roughly halves the runtime without dropping a
single exercise.

Each analysed game is cached, and cached records carry a schema version, so
adding a field to the analysis correctly invalidates old caches instead of
silently mixing formats.

### One-time setup, done manually

`setup.sh` wraps all of this, but each stage is a normal script you can run
alone:

```bash
python3 build/fetch_games.py --username YOUR_NAME   # 1
python3 build/analyze_games.py --jobs 8             # 2  (the slow one)
python3 build/weaknesses.py                         # 3  prints the report
python3 build/build_exercises.py                    # 4  writes app/exercises.js
```

---

# Make it yours

Everything personal is either gitignored or a single config value, so a fork
needs no code changes to become yours.

### Your settings

`build/coach_config.local.json` (gitignored) overrides
`build/coach_config.json` (tracked defaults), key by key. Create it by running
`./setup.sh`, or by hand:

```json
{
  "username": "your_chesscom_name",
  "time_classes": ["rapid", "blitz"],
  "months_back": 12,
  "contact": "you@example.com"
}
```

This split means `git pull` brings you improved defaults without touching your
settings, and your username never appears in a commit.

| Setting | Default | What it does |
|---------|---------|--------------|
| `time_classes` | all four | Which games to learn from. Rapid-only gives the cleanest read on your understanding; bullet mostly measures your mouse. |
| `months_back` | 6 | How much history to pull. |
| `rated_only` | true | Ignore casual games. |
| `max_games` | 400 | Cap on games analysed, newest first. |
| `engine.scan_nodes` | 150k | Effort per position in the cheap first pass. |
| `engine.verify_depth` | 18 | Depth for confirming a mistake and finding the answer. |
| `thresholds.verify_min_loss` | 100 | How bad a move must look before earning a deep search. Raise it to make analysis faster and coarser. |
| `thresholds.blunder` | 250 | Centipawns lost that counts as a blunder. |
| `exercises.lichess_per_theme` | 35 | Puzzles pulled per weak theme. |
| `exercises.rating_band` | 300 | Width of the puzzle difficulty window around your level. |

If a full analysis is too slow on your machine, the two knobs that matter most
are `max_games` and `thresholds.verify_min_loss`.

### Your repertoire

The openings in `build/repertoire.py` are just data — a list of courses, each a
list of move sequences in SAN.

```python
{
  "id": "italian", "color": "white", "tier": 1,
  "name": "Italian Game",
  "summary": "...",
  "lines": ["e4 e5 Nf3 Nc6 Bc4 Bc5 d3 Nf6 O-O", ...],
}
```

Not sure what the book continuation is? Ask the bundled ECO database:

```bash
python3 build/probe.py "e4 c6 d4 d5 e5 Bf5"
```

Then rebuild. The build **refuses** to write anything if a move you invented
isn't in the database, or if a position leaves you two different moves to play:

```bash
python3 build/generate.py
```

Because every position is verified at build time, the app itself needs no chess
engine at runtime — which is why it opens straight from a `file://` URL.

### Not a chess.com player?

`build/fetch_games.py` is the only chess.com-specific file: it turns an
account name into `data/games/index.json`, a list of records with a `pgn` field
plus `color`, `result`, `time_class` and `time_control`. Write an equivalent for
Lichess (`https://lichess.org/api/games/user/<name>`) or a folder of PGN files
and the remaining three stages work unchanged.

### Troubleshooting

**`pip3 install chess` fails with "externally-managed-environment"**
Newer Pythons refuse to install into the system interpreter. Use a virtualenv:
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install chess
```
Activate it before running the scripts. The scheduled refresh runs without your
shell, so if you use a venv, add its `bin` directory to the `PATH` line at the
top of `build/refresh.sh`.

**"stockfish not found"**
`brew install stockfish` / `sudo apt install stockfish`. If it lives somewhere
unusual, set `engine.path` in `build/coach_config.local.json` to the full path.

**"chess.com has no player called ..."**
Usernames are the ones in your profile URL (`chess.com/member/<name>`), not your
display name.

**No exercises got built**
You need finished, *rated*, standard-chess games in the time controls listed in
`time_classes`. A brand-new account, or one that only plays variants, produces
nothing. Set `"rated_only": false` or widen `time_classes` to loosen this.

**Analysis is too slow**
Lower `max_games`, raise `thresholds.verify_min_loss`, or lower
`engine.verify_depth`. You can also stop it at any point — every finished game
is already cached, so re-running picks up where it left off.

**The app shows openings but no tactics**
`app/exercises.js` is missing or empty — run `./build/refresh.sh` and check
`data/logs/`.

### Platform support

Tested on macOS. The Python pipeline is platform-independent; the only
OS-specific piece is scheduling, and `build/install_schedule.sh` uses launchd on
macOS and falls back to a crontab entry elsewhere. On Windows, run
`build/refresh.sh` under WSL or Git Bash and schedule it with Task Scheduler.

---

### Tests

```bash
node build/test_tree.js     # opening move-tree integrity
node build/test_ui.js       # opening trainer, driven in a real DOM
node build/test_coach.js    # exercises load, solve, calculation mode, report
python3 build/test_themes.py  # tactical motif detection (SEE, forks, pins…)
```

`test_coach.js` also checks the app still works **without** `exercises.js` — the
coach layer is entirely optional, and the opening trainer runs unchanged if you
never set it up.

---

## Data source & credit

Opening moves and names: **[lichess-org/chess-openings](https://github.com/lichess-org/chess-openings)**
(the ECO database Lichess itself uses), licensed CC0. Bundled in `build/eco/`.

Practice puzzles: the **[Lichess puzzle database](https://database.lichess.org/#puzzles)**,
licensed CC0. Downloaded locally, never redistributed here.

Game history: the **[chess.com public API](https://www.chess.com/news/view/published-data-api)**.

Analysis: **[Stockfish](https://stockfishchess.org/)**, which you install
yourself and which this project runs as a separate process — no Stockfish code
is included or linked here.

## License

This project is MIT (see `LICENSE`). The bundled ECO opening data in
`build/eco/` is CC0. The Lichess puzzle database is CC0 and is downloaded at
setup time rather than redistributed. Stockfish is GPL-3.0 and is used as an
external program, not bundled.

Your games, your analysis and your generated exercises never leave your
machine, and are gitignored so a fork of this repo carries none of them.
