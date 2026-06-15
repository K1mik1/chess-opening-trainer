# ♞ Opening Trainer

A small, offline, gamified app to memorize the main book moves of a focused
chess opening repertoire — built to take an ~800 player toward 1000+ in
**5–10 minutes a day** over months.

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
counted **"mastered"** once it survives to a 3-week interval.

---

## Your repertoire

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
chess-program/
├── app/                  ← THE APP (this is all you need to use it)
│   ├── index.html
│   ├── style.css
│   ├── app.js            ← board, trainer engine, spaced repetition, gamification
│   └── repertoire.js     ← generated move-tree (DB-verified). Do not hand-edit.
└── build/                ← tools to (re)generate & test the data
    ├── eco/*.tsv         ← the Lichess ECO opening database (source of truth)
    ├── repertoire.py     ← the repertoire definition (edit this to change lines)
    ├── generate.py       ← compiles + verifies repertoire.py → app/repertoire.js
    ├── probe.py          ← asks the DB "what are the book replies after <line>?"
    ├── test_tree.js      ← validates the generated tree's integrity
    └── test_ui.js        ← drives the real UI in jsdom end-to-end
```

The app needs **no chess engine at runtime**: the build precomputes the board
position (FEN), the piece's from/to squares, and the opening name for every
move. At runtime a move is simply "correct" if it matches the one book move for
that position, so there is nothing to get wrong.

### To change or grow the repertoire

1. Edit `build/repertoire.py` — add or change lines (sequences of moves).
2. Not sure what the book continuation is? Ask the database:
   ```
   python build/probe.py "e4 c6 d4 d5 e5 Bf5"
   ```
   It lists exactly the replies the master database knows, with names.
3. Rebuild (requires Python + `python-chess`):
   ```
   pip install chess
   python build/generate.py
   ```
   It **refuses to build** if any move you wrote isn't a real book move, and
   refuses if a position has two of *your* moves (ambiguous). On success it
   rewrites `app/repertoire.js`.

### To run the tests

```
python build/generate.py        # rebuild + verify every move is in book
node   build/test_tree.js        # structural integrity of the move-tree
npm i jsdom && node build/test_ui.js   # full end-to-end UI play-through
```

---

## Gamification

- **XP** for every correct move (+ bonus for a flawless line), **levels**, and a
  daily **🔥 streak**.
- **Mastery %** and ★ ratings per opening; an overall mastery ring on the home
  screen.
- **Badges**: first session, 7- and 30-day streaks, 100 moves, a flawless
  session, mastering an opening, and more.
- Little touches: move sounds, confetti on perfect lines and level-ups (toggle
  sound with 🔊 in the top bar).

---

## Data source & credit

Opening moves and names: **[lichess-org/chess-openings](https://github.com/lichess-org/chess-openings)**
(the ECO database Lichess itself uses), licensed CC0. Bundled in `build/eco/`.
