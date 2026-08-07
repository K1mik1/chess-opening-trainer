"""
Regression tests for the tactical motif detection in themes.py.

  python3 build/test_themes.py

These matter more than they look. Every weakness the coach reports, and every
themed puzzle it selects, is downstream of these functions -- a silently wrong
static exchange evaluation would mislabel which patterns you are bad at, and
you would practise the wrong thing without any error ever being raised.

The SEE cases are the standard Chess Programming Wiki positions.
"""

import sys

import chess

import themes as T

_fails = []


def check(label, got, want):
    good = got == want
    print(f"  [{'ok  ' if good else 'FAIL'}] {label:<44} = {got!s:>7}   want {want}")
    if not good:
        _fails.append(label)


def main():
    print("\nstatic exchange evaluation")
    # Rxe5 is safe: the rook on d8 does not cover e5, so it is a clean pawn.
    check("Rxe5 wins a clean pawn",
          T.see(chess.Board("1k1r4/1pp4p/p7/4p3/8/P5P1/1PP4P/2K1R3 w - -"),
                chess.Move.from_uci("e1e5")), 1)
    # Nxe5 loses material once the whole exchange plays out.
    check("Nxe5 loses the exchange",
          T.see(chess.Board("1k1r3q/1ppn3p/p4b2/4p3/8/P2N2P1/1PP1R1BP/2K1Q3 w - -"),
                chess.Move.from_uci("d3e5")), -2)
    check("Qxd5 takes an undefended queen",
          T.see(chess.Board("4k3/8/8/3q4/4Q3/8/8/4K3 w - -"),
                chess.Move.from_uci("e4d5")), 9)
    # A defended pawn (c6 covers d5): pawn takes pawn, pawn recaptures -- an
    # even trade, so the value is 0 rather than a win or a loss.
    check("exd5 into a pawn defended by c6 is even",
          T.see(chess.Board("4k3/8/2p5/3p4/4P3/8/8/4K3 w - -"),
                chess.Move.from_uci("e4d5")), 0)
    # The same capture with the defender one rank back (c7 covers b6/d6, not
    # d5) is simply a free pawn -- the distinction the SEE has to get right.
    check("exd5 with the defender on c7 is a free pawn",
          T.see(chess.Board("4k3/2p5/8/3p4/4P3/8/8/4K3 w - -"),
                chess.Move.from_uci("e4d5")), 1)

    print("\nhanging pieces")
    b = chess.Board()
    for san in ("e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"):
        b.push_san(san)
    check("Bxf7+ drops the bishop",
          T.hanging_after(b, b.parse_san("Bxf7+")), (chess.BISHOP, 3))
    # 4.O-O really does leave e4 loose to 4...Nxe4 -- a pawn, not a piece.
    check("O-O leaves the e4 pawn loose",
          T.hanging_after(b, b.parse_san("O-O")), (chess.PAWN, 1))
    check("...and one pawn is not tagged hangingPiece",
          "hangingPiece" in T.classify(b, b.parse_san("O-O"), None), False)

    print("\nmotifs")
    check("fork: Nd5-c7+ hits rook and king",
          T.is_fork(chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - -"),
                    chess.Move.from_uci("d5c7")), True)
    check("fork: a knight move hitting nothing",
          T.is_fork(chess.Board("r3k3/8/8/8/8/8/8/4K1N1 w - -"),
                    chess.Move.from_uci("g1f3")), False)
    check("pin: Ba4-b5 pins Nc6 to the king",
          "pin" in T._aligned_motifs(chess.Board("4k3/8/2n5/8/B7/8/8/4K3 w - -"),
                                     chess.Move.from_uci("a4b5")), True)
    check("skewer: Ra1-a2+, king in front of queen",
          "skewer" in T._aligned_motifs(chess.Board("8/8/8/8/8/8/4k1q1/R3K3 w - -"),
                                        chess.Move.from_uci("a1a2")), True)
    # The moving piece must actually sit on the slider's line for anything to
    # be discovered; b2-h8 runs b2,c3,d4,e5,f6,g7,h8.
    check("discovered: Nd4-f5 frees Bb2 onto Rh8",
          T.is_discovered_attack(chess.Board("7r/8/8/8/3N4/8/1B6/4K3 w - -"),
                                 chess.Move.from_uci("d4f5")), True)
    check("discovered: knight off the line reveals nothing",
          T.is_discovered_attack(chess.Board("7r/8/8/8/4N3/8/1B6/4K3 w - -"),
                                 chess.Move.from_uci("e4c5")), False)
    check("back rank: Ra8#",
          T.is_back_rank_mate(chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w Q -"),
                              chess.Move.from_uci("a1a8")), True)

    print("\ngame phase")
    check("start is the opening",
          "opening" in T.phase_themes(chess.Board()), True)
    check("bare kings and pawns is a pawn endgame",
          "pawnEndgame" in T.phase_themes(
              chess.Board("4k3/4p3/8/8/8/8/4P3/4K3 w - -")), True)
    check("rooks only is a rook endgame",
          "rookEndgame" in T.phase_themes(
              chess.Board("r3k3/8/8/8/8/8/8/R3K3 w - -")), True)

    print()
    if _fails:
        print(f"FAILED ({len(_fails)}): " + ", ".join(_fails) + "\n")
        return 1
    print("ALL THEME CHECKS PASSED ✓\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
