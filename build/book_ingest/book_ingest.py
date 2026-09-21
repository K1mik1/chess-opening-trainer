"""Ingest di un capitolo intero: dal PDF scansionato alle partite annotate.

Tre fasi separate, perche' la lettura costa e la logica cambia spesso:
  A. OCR e ritagli          (ocr_cols.py + ocr_lines.py, gia' eseguiti)
  B. lettura delle righe-mossa con il modello vision, in parallelo e con CACHE
     su disco: rilanciare la ricostruzione non ripaga le chiamate
  C. segmentazione in partite e ricostruzione vincolata alla legalita'

Le decisioni su COSA guardare si prendono sul layout e sulla legalita', mai sul
testo OCR: ogni filtro basato sull'OCR, in questo libro, ha buttato via mosse
vere (un "13" letto "3" bastava a perdere la mossa).
"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor

import chess
from PIL import Image

import vision
from boards import board_boxes, learn, read_board

# Una risposta si accetta solo se e' scritta come una mossa. Le righe di rumore
# (pezzi di diagramma, didascalie) producono 'The', 'or', 'I' -- e ogni tanto
# un 'O-O' che sarebbe perfino legale: senza questo filtro entrerebbe.
SAN_OK = re.compile(r'^(O-O(-O)?|[NBRQK]?[a-h]?[1-8]?x?[a-h][1-8](=[NBRQ])?[+#]?)[!?]*$')

CACHE = 'vision_cache.json'
RESULT = re.compile(r'\b(1-0|0-1|1/2\s*-\s*1/2|1/2)\b')

# ---------------------------------------------------------------- fase B
def prefetch(rows, workers=6):
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [r['crop'] for r in rows if r.get('crop') and r['crop'] not in cache]
    if todo:
        def work(p):
            try: return p, vision.read_move(p)
            except Exception as e: return p, None
        with ThreadPoolExecutor(workers) as ex:
            for k, (p, san) in enumerate(ex.map(work, todo), 1):
                cache[p] = san
                if k % 25 == 0:
                    print(f'  letti {k}/{len(todo)}', flush=True)
                    json.dump(cache, open(CACHE, 'w'))
        json.dump(cache, open(CACHE, 'w'))
    return cache

# ---------------------------------------------------------------- fase C
def is_move_row(r):
    return bool(r.get('reads')) and len(r['raw'].split()) <= 4

def move_number(r):
    m = re.match(r'^\s*(\d{1,2})', (r['reads'][0] or '').strip())
    return m.group(1) if m else None

def number_fits(r, expected):
    """Il numero e' un indizio rumoroso, non una chiave: l'OCR perde la prima
    cifra ("13" -> "3") e incolla la mossa ("14 f5" -> "1415")."""
    d = move_number(r)
    if d is None: return None
    exp = str(expected)
    return d == exp or exp.endswith(d) or d.startswith(exp)

GAME_HEADER = re.compile(r'\bGame\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|\d+)\b', re.I)

def is_game_header(r):
    """Il confine fra due partite.

    Il numero di mossa non puo' farlo: "10" letto a prefissi contiene "1", e
    ogni decina faceva ricominciare la partita da capo. L'intestazione stampata
    invece e' esplicita, e l'OCR della riga libera la prende quasi sempre.
    """
    for t in [r.get('raw', '')] + list(r.get('reads') or []):
        if t and GAME_HEADER.search(t): return True
    return False

def legal_from_start(san):
    try:
        chess.Board().parse_san(san.rstrip('!?')); return True
    except ValueError:
        return False

def is_prose(text):
    """Distingue una riga di testo dal rumore di un diagramma.

    Contare le parole non basta: l'ultima riga di un paragrafo e' spesso una
    parola sola ("kingside.") e veniva buttata, troncando il commento proprio
    sulla battuta finale. Il rumore dei diagrammi invece produce sigle
    maiuscole e frammenti senza vocali ("ADIWOANE", "as ae y"), quindi il
    discrimine e' la presenza di una parola scritta come si scrive una parola.
    """
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text)
    real = [w for w in words if re.search(r'[aeiou]', w[1:], re.I) and not w.isupper()]
    return bool(real)

def plausible(b):
    if len(b.pieces(chess.KING, chess.WHITE)) != 1: return False
    if len(b.pieces(chess.KING, chess.BLACK)) != 1: return False
    for c in (chess.WHITE, chess.BLACK):
        if len(b.pieces(chess.PAWN, c)) > 8: return False
    return True

PLAYERS = re.compile(r'^[A-Z][a-z]*\.?\s*[A-Z][\w\']{2,}\s*[-–]\s*[A-Z][a-z]*\.?\s*[A-Z][\w\']{2,}')

def header_of(rows, i):
    """Le righe stampate sopra la prima mossa: titolo, giocatori, torneo, apertura.

    Si guarda piu' indietro di quanto sembri necessario perche' l'intestazione
    sta spesso in cima alla colonna precedente, e la riga dei giocatori viene
    portata in testa quando la si riconosce: e' il nome con cui la partita
    comparira' nell'app.
    """
    out = []
    for r in rows[max(0, i - 16):i]:
        t = (r.get('reads') or [''])[1] if r.get('reads') and len(r['reads']) > 1 else r.get('raw', '')
        t = t.strip()
        if 3 < len(t) < 60 and re.search(r'[A-Za-z]{3}', t): out.append(t)
    named = [t for t in out if PLAYERS.match(t)]
    rest = [t for t in out if t not in named]
    return (named[-1:] + rest[-3:]) if named else out[-4:]

def build_games(rows, cache, diagram_rows):
    rows = sorted(rows + diagram_rows, key=lambda r: (r['page'], r['col'], r['top']))
    games, cur, pending = [], None, True
    board = chess.Board(); expected = 1; prose = []; model = None
    for i, r in enumerate(rows):
        if r.get('prose'):
            if cur and is_prose(r['raw']): prose.append(r['raw'])
            continue
        if r.get('diagram'):
            if not cur: continue
            img = Image.open(r['png'])
            if model is None and cur['units']:
                model = learn(img, r['box'], board.fen()); cur['checks'].append('modelli')
            elif model is not None:
                got, _ = read_board(img, r['box'], model, board.turn)
                if plausible(got):
                    cur['checks'].append('ok' if got.board_fen() == board.board_fen() else 'diverso')
            continue
        if not is_move_row(r): continue

        san = cache.get(r.get('crop')) or ''
        san = san if SAN_OK.match(san) else None
        if is_game_header(r):
            if cur: games.append(cur)
            cur, pending = None, True
        # La partita si apre alla prima mossa dopo l'intestazione che sia
        # legale dalla posizione iniziale. Cercare il numero "1" non funziona:
        # sulla prima riga l'OCR lo legge quasi sempre come "I" o lo perde.
        if cur is None and san and legal_from_start(san):
            cur = {'header': header_of(rows, i), 'page': r['page'], 'units': [], 'checks': [], 'skipped': 0, 'resync': 0}
            board = chess.Board(); expected = 1; prose = []; model = None
        if cur is None: continue
        fits = number_fits(r, expected)
        # Dopo un buco il numero atteso resta indietro e, preteso come chiave,
        # farebbe scartare tutto il resto della partita. Se la mossa letta e'
        # legale QUI e il numero stampato e' appena piu' avanti, si riallinea il
        # contatore: le risincronizzazioni vengono contate, perche' una partita
        # che ne accumula molte e' una partita da rivedere.
        if fits is False:
            d = move_number(r)
            ahead = d and d.isdigit() and 0 < int(d) - expected <= 2
            legal_here = False
            if san:
                try: board.parse_san(san.rstrip('!?')); legal_here = True
                except ValueError: legal_here = False
            if not (ahead and legal_here): continue
            expected = int(d); cur['resync'] += 1
        # numero illeggibile: si procede solo se l'OCR ha prodotto QUALCOSA su
        # quella riga. Il rumore dei diagrammi esce come stringa vuota, ed e'
        # l'unico appiglio per distinguerlo da una riga-mossa mal letta.
        if fits is None and not (r['reads'][0] or '').strip(): continue

        mv = None
        if san:
            try: mv = board.parse_san(san.rstrip('!?'))
            except ValueError: mv = None
        if mv is None:
            cur['skipped'] += 1
            continue
        if cur['units']: cur['units'][-1]['comment'] = ' '.join(prose).strip()
        cur['units'].append({'n': expected, 'side': 'w' if board.turn else 'b',
                             'san': board.san(mv), 'fen_before': board.fen(),
                             'page': r['page'], 'comment': ''})
        board.push(mv); prose = []
        if board.turn == chess.WHITE: expected += 1
        if RESULT.search(' '.join(r['reads'])):
            cur['units'][-1]['comment'] = ' '.join(prose).strip()
            games.append(cur); cur = None
    if cur: games.append(cur)
    return [g for g in games if len(g['units']) >= 10]

def diagrams(pages):
    out = []
    for p in pages:
        for c in (0, 1):
            png = f'cols/p{p}_c{c}.png'
            if not os.path.exists(png): continue
            _, boxes = board_boxes(png)
            for bx in boxes:
                out.append({'page': p, 'col': c, 'top': bx[1], 'png': png,
                            'box': bx, 'diagram': True, 'raw': '[diagramma]'})
    return out

if __name__ == '__main__':
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    rows = [r for r in json.load(open('lines.json')) if lo <= r['page'] < hi]
    move_rows = [r for r in rows if is_move_row(r)]
    print(f'righe-mossa candidate: {len(move_rows)}')
    cache = prefetch(move_rows)
    games = build_games(rows, cache, diagrams(range(lo, hi)))
    print(f'\npartite ricostruite: {len(games)}')
    for g in games:
        ok = g['checks'].count('ok'); bad = g['checks'].count('diverso')
        last = g['units'][-1]
        print(f"  p{g['page']:>3} | {len(g['units']):>3} semimosse | saltate {g['skipped']:>2} | "
              f"risync {g['resync']:>2} | "
              f"diagrammi ok {ok}/{ok+bad} | fino a {last['n']}{'.' if last['side']=='w' else '...'}{last['san']}"
              f" | {' / '.join(g['header'][:2])[:52]}")
    json.dump(games, open('chapter1.json', 'w'), indent=1)
