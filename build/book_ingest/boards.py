"""Trova e legge i diagrammi stampati nel libro.

Il diagramma e' l'unico posto in cui il libro dichiara la posizione senza
passare dalla notazione, quindi e' la prova indipendente che la trascrizione
delle mosse non e' andata alla deriva. Si individua senza cercare la scacchiera:
sotto ogni diagramma c'e' la riga delle colonne "a b c d e f g h", che l'OCR
becca sempre, e da quella si ricava il quadrato sopra.

I dodici modelli dei pezzi non si etichettano a mano: il primo diagramma di una
partita mostra una posizione che conosciamo gia' dalle prime mosse, quindi si
ritagliano le sue 64 caselle e si prendono le etichette da li'.
"""
import difflib, json, re, subprocess, csv, io
import numpy as np, chess
from PIL import Image, ImageFilter

def files_row(png):
    out = subprocess.run(['tesseract', png, '-', '--psm', '4', 'tsv'],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, errors='replace').stdout
    rows = list(csv.DictReader(io.StringIO(out), delimiter='\t', quoting=csv.QUOTE_NONE))
    lines = {}
    for r in rows:
        if not r.get('text') or not r['text'].strip(): continue
        k = (r['block_num'], r['par_num'], r['line_num'])
        L = lines.setdefault(k, {'t': [], 'l': 1e9, 'top': 1e9, 'r': 0, 'b': 0})
        L['t'].append(r['text'])
        l, t, w, h = (int(r[x]) for x in ('left', 'top', 'width', 'height'))
        L['l'], L['top'] = min(L['l'], l), min(L['top'], t)
        L['r'], L['b'] = max(L['r'], l + w), max(L['b'], t + h)
    out = []
    for L in lines.values():
        s = re.sub(r'[^a-h]', '', ''.join(L['t']).lower())
        # la riga delle colonne, tollerando gli scambi dell'OCR ("a bede#fgih")
        if len(s) >= 6 and difflib.SequenceMatcher(None, s, 'abcdefgh').ratio() >= 0.7:
            out.append(L)
    return out

def board_boxes(png):
    img = Image.open(png)
    arr = np.asarray(img.convert('L'))
    boxes = []
    for L in files_row(png):
        # le lettere sono centrate sotto le colonne, quindi da 'a' a 'h' corrono
        # sette caselle, non otto: la scacchiera sporge di mezza casella per lato
        cell = (L['r'] - L['l']) / 7.0
        x0, x1 = L['l'] - cell / 2, L['r'] + cell / 2
        bottom = L['top'] - cell * 0.12
        top = bottom - cell * 8
        if top < 0: continue
        boxes.append((int(x0), int(top), int(x1), int(bottom)))
    return img, boxes

def snap(img, box):
    """Aggancia il box ai bordi veri della cornice.

    La distanza fra la riga delle lettere e la scacchiera non e' costante nella
    scansione, quindi il box stimato va allineato: la cornice e' una riga (o
    colonna) di inchiostro quasi continuo, e basta cercarla intorno al bordo
    stimato per rimettere le 64 caselle al loro posto.
    """
    x0, y0, x1, y1 = box
    pad = int((x1 - x0) * 0.12)
    X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
    X1, Y1 = min(img.width, x1 + pad), min(img.height, y1 + pad)
    a = np.asarray(img.crop((X0, Y0, X1, Y1)).convert('L')) < 140
    rows, cols = a.mean(axis=1), a.mean(axis=0)
    def edges(prof, lo, hi):
        idx = [i for i, v in enumerate(prof) if v > 0.75]
        if not idx: return None
        return idx[0], idx[-1]
    r = edges(rows, Y0, Y1); c = edges(cols, X0, X1)
    if not r or not c: return box
    top, bot = Y0 + r[0], Y0 + r[1]
    left, right = X0 + c[0], X0 + c[1]
    if min(bot - top, right - left) < (x1 - x0) * 0.7: return box
    return (left, top, right, bot)

def squares(img, box, n=8):
    x0, y0, x1, y1 = box
    # il bordo della cornice non fa parte della scacchiera
    w, h = (x1 - x0) / n, (y1 - y0) / n
    out = {}
    for r in range(n):
        for f in range(n):
            cell = img.crop((x0 + f*w + w*0.12, y0 + r*h + h*0.12,
                             x0 + (f+1)*w - w*0.12, y0 + (r+1)*h - h*0.12)).convert('L')
            # Le case scure sono tratteggiate e il tratteggio cambia da un
            # diagramma all'altro: un filtro di massimo lo cancella (sono linee
            # sottili) e lascia i contorni spessi dei pezzi, che sono cio' che
            # distingue una casa vuota da una occupata.
            out[chess.square(f, 7 - r)] = cell.resize((28, 28), Image.LANCZOS)
    return out

def vec(cell):
    """Firma a bassa frequenza della casella.

    Il confronto pixel a pixel fallisce perche' il tratteggio delle case scure
    cambia da un diagramma all'altro: mediando su una griglia grossolana il
    tratteggio si annulla e resta la sagoma del pezzo, che e' l'unica cosa che
    deve decidere.
    """
    v = 1.0 - np.asarray(cell, dtype=float) / 255.0
    g = v.reshape(14, 2, 14, 2).mean(axis=(1, 3))   # 28x28 -> 14x14: a 7x7
                                                    # cavallo e pedone si confondono
    g = g - g.mean()
    return g.ravel() / (np.linalg.norm(g) + 1e-9)

def structure(cell):
    """Quanta struttura a bassa frequenza c'e' nella casella: una casa vuota,
    anche tratteggiata, e' piatta; un pezzo no. Serve a decidere PRIMA se la
    casa e' occupata, perche' su una casa vuota la firma normalizzata e' solo
    rumore e correlerebbe con qualsiasi modello."""
    v = 1.0 - np.asarray(cell, dtype=float) / 255.0
    return float(v.reshape(7, 4, 7, 4).mean(axis=(1, 3)).std())

def learn(img, box, fen):
    """Etichetta le 64 caselle di un diagramma la cui posizione e' gia' nota."""
    box = snap(img, box)
    b = chess.Board(fen)
    tpl = {}
    lv = {True: [], False: []}
    for sq, cell in squares(img, box).items():
        p = b.piece_at(sq)
        light = (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1
        if p: tpl.setdefault((p.symbol(), light), []).append(vec(cell))
        lv[light].append((structure(cell), bool(p)))
    thr = {}
    for light, vals in lv.items():
        occ = [s for s, o in vals if o]; emp = [s for s, o in vals if not o]
        thr[light] = (min(occ) + max(emp)) / 2 if occ and emp else 0.04
    return {'tpl': tpl, 'thr': thr}

def vecs_shifted(cell, r=2):
    """Firme della casella con piccoli scorrimenti: il ritaglio delle 64 case
    puo' slittare di qualche pixel fra un diagramma e l'altro, e uno
    scostamento del genere basta ad abbassare la somiglianza sotto quella di
    un pezzo sbagliato."""
    a = np.asarray(cell, dtype=float)
    out = []
    for dy in (-r, 0, r):
        for dx in (-r, 0, r):
            out.append(vec(Image.fromarray(np.roll(np.roll(a, dy, 0), dx, 1).astype('uint8'))))
    return out

def adaptive_threshold(vals):
    """Soglia vuoto/occupato ricavata dal diagramma stesso.

    Una soglia fissa non si trasferisce: il tratteggio delle case scure cambia
    densita' da una pagina all'altra e un valore imparato altrove marca pezzi
    dove non ce ne sono. Dentro un singolo diagramma, invece, le case vuote e
    quelle occupate formano due gruppi separati da un salto netto: basta
    cercare il salto piu' ampio nella zona centrale dei valori ordinati.
    """
    xs = sorted(vals)
    if len(xs) < 4: return 0.04
    lo, hi = max(1, len(xs)//5), min(len(xs)-1, (len(xs)*4)//5)
    gaps = [(xs[i+1] - xs[i], (xs[i+1] + xs[i]) / 2) for i in range(lo, hi)]
    return max(gaps)[1] if gaps else 0.04

def read_board(img, box, model, turn=chess.WHITE):
    tpl, learned = model['tpl'], model['thr']
    box = snap(img, box)
    b = chess.Board.empty()
    weak = []
    cells = squares(img, box)
    thr = {}
    for light in (True, False):
        # la soglia del diagramma di riferimento regge meglio di una ricavata
        # dal singolo diagramma: provata, quella adattiva perdeva pezzi veri
        thr[light] = learned[light]
    for sq, cell in cells.items():
        light = (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1
        if structure(cell) < thr[light]: continue          # casa vuota
        vs = vecs_shifted(cell)
        best = sorted(((max(float(v @ u) for v in vs for u in us), k[0])
                       for k, us in tpl.items() if k[1] == light), reverse=True)
        if not best: continue
        (s1, sym), s2 = best[0], (best[1][0] if len(best) > 1 else 0)
        if s1 - s2 < 0.05: weak.append(chess.square_name(sq))
        b.set_piece_at(sq, chess.Piece.from_symbol(sym))
    b.turn = turn
    return b, weak
