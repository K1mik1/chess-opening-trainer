"""Build a small, reproducible offline catalogue from the CC0 Lichess database.

Dependencies: python-chess, zstandard. Existing selected source rows are reused
so rebuilding never changes puzzle IDs or invalidates saved progress.
"""
import csv
import io
import json
from pathlib import Path
from urllib.request import urlopen

import chess
import zstandard
from build_exercises import make_edges

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'build' / 'public_puzzles.json'
URL = 'https://database.lichess.org/lichess_db_puzzle.csv.zst'
CATEGORIES = [
    ('mateIn1', 'Matto in una', 'Chiudi la partita con una sola mossa.'),
    ('mateIn2', 'Matto in due', 'Trova la sequenza forzata che porta al matto.'),
    ('fork', 'Forchette', 'Attacca due bersagli contemporaneamente.'),
    ('pin', 'Inchiodature', 'Sfrutta un pezzo che non può spostarsi liberamente.'),
    ('skewer', 'Infilate', 'Attacca il pezzo davanti per conquistare quello dietro.'),
    ('discoveredAttack', 'Attacchi scoperti', 'Sposta un pezzo per liberare un attacco.'),
    ('hangingPiece', 'Pezzi indifesi', 'Riconosci e cattura il materiale non protetto.'),
    ('endgame', 'Finali', 'Allena tecnica e tattica con pochi pezzi sulla scacchiera.'),
]
BANDS = [(500, 1000, 100), (1000, 1400, 100), (1400, 1801, 50)]
PER_CATEGORY = sum(count for _, _, count in BANDS)
TOTAL = len(CATEGORIES) * PER_CATEGORY


def convert(row):
    board = chess.Board(row['FEN'])
    moves = row['Moves'].split()
    # Lichess supplies the position BEFORE the opponent's setup move.
    board.push_uci(moves[0])
    start = board.fen()
    color = 'white' if board.turn else 'black'
    edges = make_edges(start, moves[1:], color)
    if not edges or len(edges) != len(moves) - 1:
        return None
    for edge in edges:
        # The trainer follows one line. Exclude ambiguous final mating moves
        # instead of rejecting another equally correct checkmate in the UI.
        if edge['mine'] and edge['san'].endswith('#'):
            mates = 0
            for move in list(board.legal_moves):
                board.push(move)
                mates += board.is_checkmate()
                board.pop()
            if mates != 1:
                return None
        board.push_uci(edge['uci'])
    return {'id': row['PuzzleId'], 'startFen': start, 'color': color,
            'edges': edges, 'myMoves': sum(e['mine'] for e in edges),
            'meta': {'kind': 'catalogue', 'title': 'Problema ' + row['PuzzleId'],
                     'rating': int(row['Rating']), 'themes': row['Themes'].split(),
                     'gameUrl': row['GameUrl'],
                     'sourceUrl': 'https://lichess.org/training/' + row['PuzzleId']}}


def select(existing):
    pools = {(theme, i): [] for theme, _, _ in CATEGORIES for i in range(3)}
    seen = set()
    positions = set()
    # Keep every published ID in its original category so local progress survives.
    for category in existing:
        for row in category['rows']:
            band = next(i for i, (lo, hi, _) in enumerate(BANDS) if lo <= int(row['Rating']) < hi)
            pools[category['theme'], band].append(row)
            seen.add(row['PuzzleId'])
            positions.add(' '.join(convert(row)['startFen'].split()[:4]))
    if len(seen) == TOTAL:
        return existing
    with urlopen(URL, timeout=60) as response:
        with zstandard.ZstdDecompressor().stream_reader(response) as stream:
            for row in csv.DictReader(io.TextIOWrapper(stream)):
                rating = int(row['Rating'])
                tags = set(row['Themes'].split())
                if (int(row['Popularity']) < 85 or int(row['NbPlays']) < 500
                        or int(row['RatingDeviation']) > 100 or 'underPromotion' in tags
                        or row['PuzzleId'] in seen):
                    continue
                slot = next(((theme, i) for theme, _, _ in CATEGORIES
                             for i, (lo, hi, count) in enumerate(BANDS)
                             if theme in tags and lo <= rating < hi
                             and len(pools[theme, i]) < count), None)
                if slot is None:
                    continue
                try:
                    item = convert(row)
                except ValueError:
                    continue
                if item is None:
                    continue
                position = ' '.join(item['startFen'].split()[:4])
                if position in positions:
                    continue
                positions.add(position)
                pools[slot].append(row)
                seen.add(row['PuzzleId'])
                if len(seen) % 250 == 0:
                    print(f'Selezionati {len(seen)}/{TOTAL}', flush=True)
                if len(seen) == TOTAL:
                    return [{'theme': theme, 'rows': sum((pools[theme, i] for i in range(3)), [])}
                            for theme, _, _ in CATEGORIES]
    raise RuntimeError('Database exhausted before filling all categories')


def main():
    existing = json.loads(SOURCE.read_text()) if SOURCE.exists() else []
    selected = select(existing)
    packs = []
    for category, (theme, name, blurb) in zip(selected, CATEGORIES):
        assert category['theme'] == theme
        items = [convert(row) for row in category['rows']]
        assert len(items) == PER_CATEGORY and all(items)
        packs.append({'id': 'lichess-' + theme, 'kind': 'catalogue', 'name': name,
                      'blurb': blurb, 'items': sorted(items, key=lambda c: c['meta']['rating'])})
    ids = [c['id'] for p in packs for c in p['items']]
    assert len(ids) == len(set(ids)) == TOTAL
    SOURCE.write_text(json.dumps(selected, ensure_ascii=False, indent=2) + '\n')
    output = {'source': 'https://database.lichess.org/#puzzles', 'license': 'CC0', 'packs': packs}
    (ROOT / 'app' / 'public-puzzles.js').write_text(
        '// Lichess puzzles, CC0. Generated by build/public_puzzles.py.\nwindow.PUBLIC_PUZZLES = '
        + json.dumps(output, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print(f'{TOTAL} problemi verificati, {len(CATEGORIES)} categorie, {len(BANDS)} fasce di difficoltà.')


if __name__ == '__main__':
    main()
