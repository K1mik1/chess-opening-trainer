"""
Repertoire definition for the opening trainer.

Every line is a sequence of SAN moves (no move numbers). build/generate.py
replays each line with python-chess and verifies that every move is a real book
move (the position occurs in the Lichess ECO database, build/eco/*.tsv). The
build ABORTS on any move that leaves known theory, so nothing here is invented.

Each course is one opening the user trains. `color` = the side the user plays;
the other side is played automatically and the user is quizzed on their moves.
`tier` (1 = Beginner, 2 = Intermediate) drives the learning curve: courses are
listed in teaching order, and the daily scheduler introduces new lines starting
from the top, so foundational openings are learned first.

Branching happens at the OPPONENT's moves (each reply becomes a variation the
app can quiz). At the USER's moves there must be exactly ONE book move per
position; generate.py enforces this.

NOTE on "most-played lines": the masters frequency API was unreachable from the
build host, so the sidelines below are the established main variations (which
are also the most-played), each verified to exist in the ECO database. Lines
end where the database's named theory ends.
"""

REPERTOIRE = [

    # ============================================================
    # TIER 1  --  BEGINNER (learn these first)
    # ============================================================

    {
        "id": "italian", "color": "white", "tier": 1,
        "name": "Italian Game",
        "summary": "1.e4 e5 2.Nf3 Nc6 3.Bc4 -- the classic, principled opening. "
                   "We play the modern slow Italian (Giuoco Pianissimo): develop, "
                   "castle, build the centre with c3 and d3. A perfect first opening.",
        "lines": [
            "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O Re1 a6 Bb3 Ba7 h3",
            "e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Bc5 O-O d6 c3 O-O",
            "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 d6 d4 exd4 cxd4 Bb6",
        ],
    },

    {
        "id": "scotch", "color": "white", "tier": 1,
        "name": "Scotch Game",
        "summary": "1.e4 e5 2.Nf3 Nc6 3.d4 -- strike the centre at once. After 3...exd4 "
                   "4.Nxd4 White gets easy development and open lines, with far less "
                   "theory than the Ruy Lopez. Very natural to play.",
        "lines": [
            # 4...Bc5 Classical
            "e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Bc5 Be3 Qf6 c3 Nge7 Qd2",
            # 4...Nf6 Mieses Variation
            "e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nxc6 bxc6 e5",
            # 4...Qh4 (Steinitz) aggressive try
            "e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Qh4 Nb5 Bb4 Bd2 Qxe4 Be2 Kd8 O-O Bxd2",
        ],
    },

    {
        "id": "vienna", "color": "white", "tier": 1,
        "name": "Vienna Game",
        "summary": "1.e4 e5 2.Nc3 then 3.Bc4 (the Stanley Variation) -- quick "
                   "development with attacking ideas. Greedy ...Nxe4 walks into the "
                   "famous Frankenstein-Dracula attack. Common and tricky below 1200.",
        "lines": [
            # 3...Nxe4 -- Frankenstein-Dracula (DB-verified main line)
            "e4 e5 Nc3 Nf6 Bc4 Nxe4 Qh5 Nd6 Bb3 Nc6 Nb5 g6 Qf3 f5 Qd5 Qe7 Nxc7 Kd8 Nxa8 b6",
            # 3...Nc6 quiet (Vienna Hybrid)
            "e4 e5 Nc3 Nf6 Bc4 Nc6 d3 Bb4 Ne2",
            # 3...Bc5 quiet (Spielmann Attack)
            "e4 e5 Nc3 Nf6 Bc4 Bc5 d3 Nc6",
        ],
    },

    {
        "id": "scandinavian", "color": "white", "tier": 1,
        "name": "Scandinavian Defense",
        "summary": "Our answer to 1...d5. We take with 2.exd5 and, after Black "
                   "recaptures the queen, gain time by chasing it with Nc3 and build a "
                   "big centre. Easy and pleasant for White.",
        "lines": [
            "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 Bf5 Ne5 c6",
            "e4 d5 exd5 Qxd5 Nc3 Qd6 d4 Nf6 Nf3 a6",
            "e4 d5 exd5 Nf6 d4 Nxd5 Nf3 g6",
        ],
    },

    {
        "id": "london", "color": "white", "tier": 1,
        "name": "London System",
        "summary": "A 1.d4 system: d4, Nf3, Bf4, e3, c3, Bd3 -- almost the same setup "
                   "against anything Black does. Very low theory, super solid, and one "
                   "of the most popular openings below 1200. Your reliable queen's-pawn "
                   "weapon.",
        "lines": [
            # vs ...d5 with ...c5
            "d4 d5 Nf3 Nf6 Bf4 c5 e3 Nc6 Nbd2 e6 c3",
            # vs ...g6 (King's Indian setups)
            "d4 Nf6 Nf3 g6 Bf4 Bg7 e3 d6 Be2 O-O",
            # Poisoned-pawn try ...Qb6
            "d4 Nf6 Nf3 d5 Bf4 c5 e3 Qb6 Nc3",
        ],
    },

    {
        "id": "queens_gambit", "color": "white", "tier": 1,
        "name": "Queen's Gambit",
        "summary": "1.d4 d5 2.c4 -- the most principled queen's-pawn opening. We offer "
                   "the c-pawn to deflect Black's centre, then dominate with Nc3, Bg5, "
                   "e3. A cornerstone opening every improving player should know.",
        "lines": [
            # Queen's Gambit Declined, main
            "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6 Bh4 b6",
            # Queen's Gambit Accepted
            "d4 d5 c4 dxc4 Nf3 Nf6 e3 e6 Bxc4 c5 O-O a6",
            # Slav move-order (2...c6) -> Meran
            "d4 d5 c4 c6 Nf3 Nf6 Nc3 e6 e3 Nbd7 Bd3 dxc4 Bxc4 b5",
        ],
    },

    # ============================================================
    # TIER 2  --  INTERMEDIATE
    # ============================================================

    {
        "id": "ruy_lopez", "color": "white", "tier": 2,
        "name": "Ruy Lopez (Spanish)",
        "summary": "1.e4 e5 2.Nf3 Nc6 3.Bb5 -- the most respected e4 opening, pressuring "
                   "Black's knight and centre. More theory than the Italian, but the "
                   "main lines are deeply logical and worth knowing as you climb.",
        "lines": [
            # Closed Ruy main line
            "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qc7",
            # Open Ruy
            "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Nxe4 d4 b5 Bb3 d5 dxe5 Be6 c3 Bc5",
            # Berlin Defense
            "e4 e5 Nf3 Nc6 Bb5 Nf6 O-O Nxe4 d4 Nd6 Bxc6 dxc6 dxe5 Nf5 Qxd8 Kxd8",
        ],
    },

    {
        "id": "alapin", "color": "white", "tier": 2,
        "name": "Sicilian Defense: Alapin (2.c3)",
        "summary": "Our answer to 1...c5. The Alapin (2.c3) sidesteps mainline Sicilian "
                   "theory and aims for a big pawn centre with d4. Solid and low-theory "
                   "-- ideal for sub-1500 play.",
        "lines": [
            # vs 2...d5 -- Barmen, central exchange
            "e4 c5 c3 d5 exd5 Qxd5 d4 cxd4 cxd4 Nc6 Nf3 Bg4 Nc3 Bxf3 gxf3",
            # vs 2...d5 -- Barmen, modern with ...Nf6
            "e4 c5 c3 d5 exd5 Qxd5 d4 Nf6 Nf3 Bg4",
            # vs 2...Nf6 -- Stoltz Attack
            "e4 c5 c3 Nf6 e5 Nd5 Nf3 Nc6 Bc4 Nb6 Bb3 c4 Bc2",
        ],
    },

    {
        "id": "french_advance", "color": "white", "tier": 2,
        "name": "French Defense: Advance (3.e5)",
        "summary": "Our answer to 1...e6. The Advance grabs space with 3.e5 and gives "
                   "White a clear plan: hold d4, attack on the kingside. Pairs naturally "
                   "with the Caro-Kann Advance.",
        "lines": [
            "e4 e6 d4 d5 e5 c5 c3 Nc6 Nf3 Qb6 a3 Nh6",
            "e4 e6 d4 d5 e5 c5 c3 Qb6 Nf3 Bd7",
            "e4 e6 d4 d5 e5 c5 c3 Nc6 Nf3 Bd7",
        ],
    },

    {
        "id": "caro_kann", "color": "black", "tier": 2,
        "name": "Caro-Kann Defense",
        "summary": "Our answer to 1.e4. Rock-solid: 1...c6 then 2...d5 hits the centre "
                   "with a safe structure and an easy light-squared bishop. Much less "
                   "theory than 1...e5 and very hard to crack.",
        "lines": [
            "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 h5 Bh7 Bd3 Bxd3 Qxd3 e6 Bd2 Ngf6 O-O-O Be7",
            "e4 c6 d4 d5 Nd2 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 h5 Bh7 Bd3 Bxd3 Qxd3 e6 Bd2 Ngf6 O-O-O Be7",
            "e4 c6 d4 d5 e5 Bf5 c3 e6 Be2",
            "e4 c6 d4 d5 e5 Bf5 Nc3 e6 g4 Bg6 Nge2 c5",
            "e4 c6 d4 d5 exd5 cxd5 Bd3 Nc6 c3 Nf6 Bf4",
            "e4 c6 d4 d5 exd5 cxd5 c4 Nf6 Nc3 e6 Nf3 Bb4",
        ],
    },

    {
        "id": "petrov", "color": "black", "tier": 2,
        "name": "Petrov (Russian) Defense",
        "summary": "Our second answer to 1.e4: 1...e5 2.Nf3 Nf6 -- instead of defending "
                   "the e5-pawn, counterattack e4. Symmetrical, solid, and famously hard "
                   "to beat. Just remember 3.Nxe5 d6! first (never 3...Nxe4??).",
        "lines": [
            # Classical Attack, Chigorin main line
            "e4 e5 Nf3 Nf6 Nxe5 d6 Nf3 Nxe4 d4 d5 Bd3 Be7 O-O Nc6 Re1 Bg4 c3 f5",
            # Cochrane Gambit (a common surprise weapon below 1200)
            "e4 e5 Nf3 Nf6 Nxe5 d6 Nxf7 Kxf7",
            # Modern Attack (3.d4)
            "e4 e5 Nf3 Nf6 d4 Nxe4 Bd3 d5 Nxe5 Bd6 O-O O-O c4",
            # 3.Nc3 -> Four Knights
            "e4 e5 Nf3 Nf6 Nc3 Nc6 Bb5 Bb4 O-O O-O d3 d6",
        ],
    },

    {
        "id": "slav", "color": "black", "tier": 2,
        "name": "Slav Defense",
        "summary": "Our answer to 1.d4. The Slav (1...d5, 2...c6) supports the centre "
                   "with a pawn instead of locking in the light bishop. Thematically "
                   "similar to the Caro-Kann, so the two reinforce each other.",
        "lines": [
            "d4 d5 c4 c6 Nf3 Nf6 Nc3 dxc4 a4 Bf5 e3 e6 Bxc4 Bb4 O-O O-O",
            "d4 d5 c4 c6 Nc3 Nf6 Nf3 dxc4 a4 Bf5 e3 e6 Bxc4 Bb4",
            "d4 d5 c4 c6 cxd5 cxd5 Nc3 Nf6 Nf3 Nc6 Bf4 Bf5 e3 e6",
            "d4 d5 c4 c6 Nf3 Nf6 e3 Bf5 cxd5 cxd5 Qb3 Qc8",
        ],
    },
]
