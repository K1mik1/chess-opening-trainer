"""Probe: given a SAN line, list the book replies the ECO database knows.
Usage: python build/probe.py "e4 e6 d4 d5 e5 c5 c3 Nc6 Nf3 Qb6 a3"
"""
import sys
import chess
from generate import load_eco

book_epds, name_by_epd = load_eco()
line = sys.argv[1].split()
board = chess.Board()
for san in line:
    board.push_san(san)

print(f"After: {' '.join(line) or '(start)'}")
print(f"  this position in book? {board.epd() in book_epds}")
name = name_by_epd.get(board.epd())
if name:
    print(f"  named: {name}")
print("  book replies:")
found = []
for move in board.legal_moves:
    board.push(move)
    if board.epd() in book_epds:
        nm = name_by_epd.get(board.epd(), "")
        found.append((board.san(chess.Move.from_uci(move.uci())) if False else None, move))
        san = chess.Board(board.fen())  # noop
    board.pop()
for move in board.legal_moves:
    san = board.san(move)
    board.push(move)
    if board.epd() in book_epds:
        nm = name_by_epd.get(board.epd(), "")
        print(f"    {san:<7} {nm}")
    board.pop()
