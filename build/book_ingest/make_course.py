"""Dalle partite estratte al file che l'app importa.

Il file resta FUORI dal repo pubblico: l'app lo carica dal dispositivo e lo
tiene in IndexedDB. Qui si aggiunge la posizione risultante di ogni mossa, cosi'
il client non deve conoscere le regole degli scacchi per disegnare la scacchiera.
"""
import json, re
import chess

def clean(t):
    """Ripulisce gli artefatti OCR piu' grossolani senza riscrivere il testo:
    il commento e' dell'autore, non va reinventato."""
    t = re.sub(r'\s+', ' ', t or '').strip()
    t = t.replace('’', "'").replace('‘', "'")
    t = re.sub(r'\s+([,.;:!?])', r'\1', t)
    return t

games = json.load(open('chapter1.json'))
out = []
for gi, g in enumerate(games, 1):
    head = [h for h in g['header'] if h]
    players = next((h for h in head if re.search(r'\w\.?\s*\w+\s*[-–]\s*\w', h)), f'Partita {gi}')
    board = chess.Board()
    moves = []
    for u in g['units']:
        try: mv = board.parse_san(u['san'])
        except ValueError: break
        board.push(mv)
        moves.append({'n': u['n'], 'side': u['side'], 'san': u['san'],
                      'fen': board.fen(), 'from': chess.square_name(mv.from_square),
                      'to': chess.square_name(mv.to_square),
                      'comment': clean(u['comment'])})
    out.append({'id': f'mcd-ch1-g{gi}', 'players': clean(players),
                'event': clean(next((h for h in head if h != players), '')),
                'moves': moves,
                'flags': {'skipped': g['skipped'], 'resync': g['resync']}})

course = {'id': 'mcdonald-logical-thinking-ch1',
          'title': 'Classical Chess Thinking: 1 e4 e5',
          'book': 'Chess: The Art of Logical Thinking — Neil McDonald',
          'games': out}
json.dump(course, open('course-mcdonald-ch1.json', 'w'), ensure_ascii=False, indent=1)
print(f"partite: {len(out)}")
for g in out:
    print(f"  {g['players'][:40]:<42} {len(g['moves']):>3} mosse | "
          f"{sum(1 for m in g['moves'] if len(m['comment'])>80)} con commento")
