"""
Tactical theme detection.

Given a position, the move actually played, and the engine's best move, work
out WHAT KIND of mistake was made -- "you hung a piece", "you missed a fork",
"you allowed a back-rank mate".

Theme names deliberately match the tags used by the Lichess puzzle database,
so a weakness measured in your own games translates directly into a filter for
fresh practice puzzles on the same theme.

Everything here is a heuristic over the actual board, not an engine call, so it
is fast and runs on every flagged position.
"""

import chess

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
         chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}

# Human-readable labels, shown in the app.
LABELS = {
    "hangingPiece":     "Leaving a piece undefended",
    "fork":             "Forks (one piece, two targets)",
    "pin":              "Pins",
    "skewer":           "Skewers",
    "discoveredAttack": "Discovered attacks",
    "backRankMate":     "Back-rank weakness",
    "mateIn1":          "One-move mates",
    "mateIn2":          "Mate in two",
    "mateIn3":          "Longer forced mates",
    "trappedPiece":     "Trapped pieces",
    "promotion":        "Pawn promotion races",
    "capturingDefender": "Removing the defender",
    "exposedKing":      "King safety",
    "advancedPawn":     "Advanced passed pawns",
    "endgame":          "Endgame technique",
    "rookEndgame":      "Rook endgames",
    "pawnEndgame":      "King and pawn endgames",
    "queenEndgame":     "Queen endgames",
    "opening":          "Opening play",
    "middlegame":       "Middlegame play",
}


# ---------------------------------------------------------------------------
# Static exchange evaluation
# ---------------------------------------------------------------------------

def see(board, move):
    """Static exchange evaluation, in pawns, for the side making `move`.

    Plays the capture, then lets each side in turn recapture on the target
    square with its least valuable attacker, stopping whenever continuing the
    exchange would lose material. Positive means the exchange wins material.

    python-chess has no built-in SEE. Rather than the usual bitboard swap
    algorithm, this recurses through real move generation: slower, but it gets
    x-rays, pins and promotions right for free, because a piece that cannot
    legally recapture simply never appears as an option.
    """
    victim = board.piece_at(move.to_square)
    gained = VALUE.get(victim.piece_type, 0) if victim else 0
    after = board.copy(stack=False)
    after.push(move)
    return gained - _recapture_value(after, move.to_square)


def _recapture_value(board, target):
    """Best material the side to move can win by recapturing on `target`.

    Returns 0 when declining the recapture is better -- that "stand pat" option
    is what stops a favourable exchange from being scored as a loss.
    """
    on_target = board.piece_at(target)
    if on_target is None:
        return 0

    cheapest, cheapest_val = None, 999
    for move in board.generate_legal_moves(to_mask=chess.BB_SQUARES[target]):
        piece = board.piece_at(move.from_square)
        if piece is None:
            continue
        value = VALUE.get(piece.piece_type, 0)
        if value < cheapest_val:
            cheapest, cheapest_val = move, value
    if cheapest is None:
        return 0

    captured = VALUE.get(on_target.piece_type, 0)
    after = board.copy(stack=False)
    after.push(cheapest)
    return max(0, captured - _recapture_value(after, target))


def hanging_after(board, move):
    """After `move`, what is the most valuable thing the opponent wins for free?

    Returns (piece_type, gain_in_pawns) for the opponent's best winning
    capture, or None if nothing is loose. This is the single most common
    sub-1200 error: a move that simply leaves something en prise.
    """
    after = board.copy(stack=False)
    after.push(move)
    best = None
    for reply in after.legal_moves:
        if not after.is_capture(reply):
            continue
        gain = see(after, reply)
        if gain > 0 and (best is None or gain > best[1]):
            victim = after.piece_at(reply.to_square)
            best = (victim.piece_type if victim else chess.PAWN, gain)
    return best


# ---------------------------------------------------------------------------
# Individual motif detectors -- all evaluate the position AFTER `move`
# ---------------------------------------------------------------------------

def _valuable_targets(board, square, mover_color):
    """Enemy pieces attacked from `square` that are worth winning.

    A target counts if it is more valuable than the attacker, or is
    undefended, or is the king (i.e. the attack is a real threat).
    """
    piece = board.piece_at(square)
    if piece is None:
        return []
    my_val = VALUE.get(piece.piece_type, 0)
    hits = []
    for sq in board.attacks(square):
        victim = board.piece_at(sq)
        if victim is None or victim.color == mover_color:
            continue
        defended = board.is_attacked_by(not mover_color, sq)
        if victim.piece_type == chess.KING:
            hits.append((sq, VALUE[chess.KING]))
        elif VALUE.get(victim.piece_type, 0) > my_val or not defended:
            hits.append((sq, VALUE.get(victim.piece_type, 0)))
    return hits


def is_fork(board, move):
    """`move` lands a piece that now attacks two or more worthwhile targets.

    At least one target has to be a real piece (or the king). Hitting two
    loose pawns is a double attack, but it is not the pattern that costs
    beginners games, and counting it as one buries the ones that do.
    """
    after = board.copy(stack=False)
    mover = board.turn
    after.push(move)
    targets = _valuable_targets(after, move.to_square, mover)
    return len(targets) >= 2 and any(v >= 3 for _sq, v in targets)


def _aligned_motifs(board, move):
    """Detect pin and skewer created by a sliding move.

    Both motifs are the same geometry -- a slider, an enemy piece, and a second
    enemy piece behind it on the same line. It is a SKEWER when the front piece
    is worth more than the back one (the valuable piece must move and the one
    behind falls), and a PIN otherwise (the front piece is stuck).
    """
    after = board.copy(stack=False)
    mover = board.turn
    after.push(move)
    piece = after.piece_at(move.to_square)
    if piece is None or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return set()

    found = set()
    origin = move.to_square
    for direction in _ray_dirs(piece.piece_type):
        first = second = None
        sq = origin
        while True:
            sq = _step(sq, direction)
            if sq is None:
                break
            occupant = after.piece_at(sq)
            if occupant is None:
                continue
            if occupant.color == mover:
                break                      # our own piece blocks the line
            if first is None:
                first = occupant
            else:
                second = occupant
                break
        if first is not None and second is not None:
            fv, sv = VALUE.get(first.piece_type, 0), VALUE.get(second.piece_type, 0)
            back_is_king = second.piece_type == chess.KING
            if fv > sv and fv >= 3:
                # front piece is the valuable one: it must move, and what is
                # behind it falls
                found.add("skewer")
            elif back_is_king or sv > fv:
                # front piece is stuck, because moving it exposes something
                # worth more. Only worth the name if there is something to win.
                if back_is_king or sv >= 3:
                    found.add("pin")
            # equal values (pawn behind pawn, knight behind bishop) are just an
            # alignment, not a motif -- naming them here was inflating "Pins"
            # into the top weakness and filling the drill set with noise.
    return found


def _ray_dirs(piece_type):
    diag = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    straight = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if piece_type == chess.BISHOP:
        return diag
    if piece_type == chess.ROOK:
        return straight
    return diag + straight


def _step(square, direction):
    f = chess.square_file(square) + direction[0]
    r = chess.square_rank(square) + direction[1]
    if 0 <= f < 8 and 0 <= r < 8:
        return chess.square(f, r)
    return None


def is_discovered_attack(board, move):
    """Moving off a line reveals a friendly slider's attack on something big."""
    mover = board.turn
    after = board.copy(stack=False)
    after.push(move)

    for slider_sq in after.pieces(chess.QUEEN, mover) | after.pieces(chess.ROOK, mover) \
            | after.pieces(chess.BISHOP, mover):
        if slider_sq == move.to_square:
            continue                        # that's the piece that just moved
        was = board.attacks(slider_sq) if board.piece_at(slider_sq) else chess.SquareSet()
        now = after.attacks(slider_sq)
        for sq in now - was:
            victim = after.piece_at(sq)
            if victim and victim.color != mover and VALUE.get(victim.piece_type, 0) >= 3:
                return True
    return False


def is_back_rank_mate(board, move):
    """Mate delivered on the defender's own back rank by a rook or queen."""
    after = board.copy(stack=False)
    mover = board.turn
    after.push(move)
    if not after.is_checkmate():
        return False
    piece = after.piece_at(move.to_square)
    if piece is None or piece.piece_type not in (chess.ROOK, chess.QUEEN):
        return False
    king_sq = after.king(not mover)
    if king_sq is None:
        return False
    back_rank = 0 if not mover == chess.WHITE else 7
    return chess.square_rank(king_sq) == back_rank


def is_trapped_piece(board, move):
    """After `move`, one of the mover's own pieces has no safe square left.

    Applied to a mistake, this is the "my bishop went somewhere it can never
    come back from" error.
    """
    after = board.copy(stack=False)
    mover = board.turn
    after.push(move)

    for sq in chess.scan_forward(after.occupied_co[mover]):
        piece = after.piece_at(sq)
        if piece is None or piece.piece_type in (chess.KING, chess.PAWN):
            continue
        if VALUE.get(piece.piece_type, 0) < 3:
            continue
        if not after.is_attacked_by(not mover, sq):
            continue                       # not under threat, so not trapped
        # can it reach any square where it isn't simply lost?
        escaped = False
        probe = after.copy(stack=False)
        probe.turn = mover
        for esc in probe.generate_legal_moves(from_mask=chess.BB_SQUARES[sq]):
            if see(probe, esc) >= 0 and not probe.is_attacked_by(not mover, esc.to_square):
                escaped = True
                break
            if see(probe, esc) >= 0:
                escaped = True
                break
        if not escaped:
            return True
    return False


# ---------------------------------------------------------------------------
# Phase / material tags
# ---------------------------------------------------------------------------

def phase_themes(board):
    """Opening / middlegame / endgame, plus the endgame's piece character."""
    pieces = [board.piece_at(sq) for sq in chess.scan_forward(board.occupied)]
    non_pawn = [p for p in pieces if p and p.piece_type not in (chess.PAWN, chess.KING)]
    material = sum(VALUE.get(p.piece_type, 0) for p in non_pawn)

    tags = set()
    if material <= 13:
        tags.add("endgame")
        kinds = {p.piece_type for p in non_pawn}
        if not kinds:
            tags.add("pawnEndgame")
        elif kinds == {chess.ROOK}:
            tags.add("rookEndgame")
        elif kinds == {chess.QUEEN}:
            tags.add("queenEndgame")
        elif kinds == {chess.KNIGHT}:
            tags.add("knightEndgame")
        elif kinds == {chess.BISHOP}:
            tags.add("bishopEndgame")
    elif board.fullmove_number <= 12:
        tags.add("opening")
    else:
        tags.add("middlegame")
    return tags


# ---------------------------------------------------------------------------
# Top-level classifier
# ---------------------------------------------------------------------------

def classify(board, played, best, mate_before=None, mate_after=None, pv=None):
    """Tag a mistake made in `board` where `played` was chosen over `best`.

    Two different questions get asked of the position, because a mistake has
    two halves:
      * what did the played move ALLOW?   -> looked for after `played`
      * what did the best move OFFER?     -> looked for after `best`
    Both sets of tags are returned together; a fork you failed to spot and a
    fork you walked into are the same pattern to practise.
    """
    tags = set()
    tags |= phase_themes(board)

    # --- what the played move allowed ---
    loose = hanging_after(board, played)
    if loose and loose[1] >= 2:
        tags.add("hangingPiece")
    if is_trapped_piece(board, played):
        tags.add("trappedPiece")

    # the opponent's refutation is where the real motif usually lives
    after_played = board.copy(stack=False)
    after_played.push(played)
    refutation = pv[0] if pv else None
    if refutation and refutation in after_played.legal_moves:
        if is_fork(after_played, refutation):
            tags.add("fork")
        tags |= _aligned_motifs(after_played, refutation)
        if is_discovered_attack(after_played, refutation):
            tags.add("discoveredAttack")
        if is_back_rank_mate(after_played, refutation):
            tags.add("backRankMate")

    # --- what the best move offered ---
    if best and best in board.legal_moves:
        if is_fork(board, best):
            tags.add("fork")
        tags |= _aligned_motifs(board, best)
        if is_discovered_attack(board, best):
            tags.add("discoveredAttack")
        if is_back_rank_mate(board, best):
            tags.add("backRankMate")
        if board.is_capture(best) and see(board, best) >= 2:
            tags.add("capturingDefender")
        piece = board.piece_at(best.from_square)
        if piece and piece.piece_type == chess.PAWN:
            rank = chess.square_rank(best.to_square)
            if rank in (0, 7):
                tags.add("promotion")
            elif (board.turn == chess.WHITE and rank >= 5) or \
                 (board.turn == chess.BLACK and rank <= 2):
                tags.add("advancedPawn")

    # --- mate motifs, straight from the engine score ---
    if mate_before is not None and 0 < mate_before <= 3:
        tags.add(f"mateIn{mate_before}")
    if mate_after is not None and mate_after < 0:
        tags.add("exposedKing")

    return tags
