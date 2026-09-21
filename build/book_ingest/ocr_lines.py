"""Secondo passaggio: le righe-mossa vanno lette da sole.

Tesseract sul paragrafo sbanda sulle righe brevi e centrate ("2  Nf3" diventa
"2 AB") perche' non ha contesto linguistico e la figurina lo confonde. Ma quelle
righe si riconoscono dal LAYOUT prima che dal contenuto: poche parole, corte,
staccate. Le individuo dal TSV di tesseract, poi ritaglio ciascuna e la rileggo
con --psm 7 (riga singola) e una whitelist di caratteri: alla casa d'arrivo
serve solo l'alfabeto delle coordinate, e togliere tutto il resto elimina quasi
tutti gli scambi di carattere.
"""
import csv, io, json, os, re, subprocess, sys
from PIL import Image
import numpy as np
from glyphs import glyph_of, blobs

def tsv_lines(png):
    out = subprocess.run(['tesseract', png, '-', '--psm', '4', 'tsv'],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors='replace').stdout
    rows = list(csv.DictReader(io.StringIO(out), delimiter='\t', quoting=csv.QUOTE_NONE))
    lines = {}
    for r in rows:
        if not r.get('text') or not r['text'].strip(): continue
        key = (r['block_num'], r['par_num'], r['line_num'])
        L = lines.setdefault(key, {'words': [], 'l': 1e9, 't': 1e9, 'r': 0, 'b': 0})
        L['words'].append(r['text'])
        l, t, w, h = (int(r[k]) for k in ('left', 'top', 'width', 'height'))
        L['l'], L['t'] = min(L['l'], l), min(L['t'], t)
        L['r'], L['b'] = max(L['r'], l + w), max(L['b'], t + h)
    return list(lines.values())

def reread(img, box):
    """Due letture della stessa riga: con la whitelist delle coordinate e senza.
    Sbagliano in modo diverso -- la whitelist salva le case ma cancella il
    glifo, la lettura libera tiene il glifo e storpia le case -- e tenerle
    entrambe da' al matcher due possibilita' di azzeccare la casa giusta.
    L'ingrandimento e' 3x: a 5x tesseract peggiora (f3 diventa 13)."""
    crop = img.crop(box)
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    crop.save('_line.png')
    reads = []
    for extra in (['-c', 'tessedit_char_whitelist=0123456789abcdefghxX+#=O-.'], []):
        reads.append(subprocess.run(
            ['tesseract', '_line.png', '-', '--psm', '7'] + extra,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, errors='replace').stdout.strip())
    return reads

def harvest(pages):
    found = []
    for p in pages:
        for c in (0, 1):
            png = f'cols/p{p}_c{c}.png'
            img = Image.open(png)
            W = img.width
            all_lines = sorted(tsv_lines(png), key=lambda L: L['t'])
            # Interlinea tipica della colonna: serve a capire quali righe sono
            # STACCATE dal testo. Una mossa principale ha spazio bianco sopra e
            # sotto; una mossa citata dentro un paragrafo (una variante) no, ed
            # e' l'unico modo per non prendere le varianti per mosse giocate.
            tops = [L['t'] for L in all_lines]
            gaps = sorted(b - a for a, b in zip(tops, tops[1:])) or [1]
            lead = gaps[len(gaps)//2] or 1
            isolated = set()
            for k, L in enumerate(all_lines):
                up = L['t'] - all_lines[k-1]['b'] if k else 10**6
                dn = all_lines[k+1]['t'] - L['b'] if k+1 < len(all_lines) else 10**6
                if up > lead * 0.55 and dn > lead * 0.55: isolated.add(id(L))
            # Il margine sinistro vero della colonna: la prosa e' giustificata e ci
            # si appoggia quasi sempre, quindi il bordo si ricava dalle righe stesse.
            lefts = sorted(L['l'] for L in all_lines)
            margin = lefts[len(lefts)//5] if lefts else 0
            for L in all_lines:
                text = ' '.join(L['words'])
                width = L['r'] - L['l']
                # Firma di una riga-mossa: poche parole, riga corta e soprattutto
                # INDENTATA. E' questo a separarla dall'ultima riga di un paragrafo,
                # che e' altrettanto corta ma parte dal margine.
                # Criterio principale: riga corta e INDENTATA rispetto al
                # margine della colonna. Ma non tutte le mosse sono indentate
                # (dopo un diagramma capita che siano allineate a sinistra),
                # quindi vale anche la forma minima "numero + una parola corta",
                # che nella prosa non compare praticamente mai.
                short_numeric = (len(L['words']) <= 3 and len(text) <= 12
                                 and re.match(r'^\s*\d{1,2}\b', text)
                                 and id(L) in isolated)
                is_move = (len(L['words']) <= 4 and width < W * 0.70
                           and (L['l'] > margin + W * 0.10 or short_numeric))
                if not is_move:
                    # la prosa serve come commento della mossa che la precede
                    found.append({'page': p, 'col': c, 'top': L['t'], 'raw': text,
                                  'prose': True, 'box': [L['l'], L['t'], L['r'], L['b']]})
                    continue
                if True:
                    reads = reread(img, (max(0, L['l'] - 20), max(0, L['t'] - 14),
                                         min(W, L['r'] + 20), L['b'] + 14))
                    # terza lettura: solo il blocco della mossa, isolato dal numero
                    # e dai puntini. Su una riga cosi' corta tesseract sbaglia meno.
                    blk, _ = glyph_of(img, (L['l'], L['t'], L['r'], L['b']))
                    if blk is not None and blk.width > 8:
                        # due varianti: il blocco intero e il blocco senza il primo
                        # carattere. Se quel carattere e' la figurina, toglierla
                        # lascia la sola casa e tesseract smette di storpiarla
                        # ("Ba4" letto "ad" diventa "a4").
                        variants = [blk]
                        gs = blobs(np.asarray(blk.convert('L')), gap=2)
                        if len(gs) >= 2:
                            variants.append(blk.crop((gs[1][0] - 2, 0, blk.width, blk.height)))
                        for v in variants:
                            if v.width < 6: continue
                            v.resize((v.width * 3, v.height * 3), Image.LANCZOS).save('_blk.png')
                            reads.append(subprocess.run(
                                ['tesseract', '_blk.png', '-', '--psm', '8',
                                 '-c', 'tessedit_char_whitelist=0123456789abcdefghxX+#=O-'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, errors='replace').stdout.strip())
                    # il ritaglio resta su disco: se la catena locale non
                    # decide, e' questo che va al modello vision
                    os.makedirs('crops', exist_ok=True)
                    cp = f"crops/p{p}c{c}_{L['t']}.png"
                    img.crop((max(0, L['l'] - 20), max(0, L['t'] - 14),
                              min(W, L['r'] + 20), L['b'] + 14)).save(cp)
                    found.append({'page': p, 'col': c, 'top': L['t'],
                                  'raw': text, 'clean': reads[0], 'reads': reads,
                                  'crop': cp, 'box': [L['l'], L['t'], L['r'], L['b']]})
    return found

if __name__ == '__main__':
    res = harvest(range(int(sys.argv[1]), int(sys.argv[2])))
    json.dump(res, open('lines.json', 'w'), indent=1)
    for r in [x for x in res if x.get('reads')][:40]:
        print(f"p{r['page']}c{r['col']}  psm4={r['raw']!r:26}  letture={r['reads']}")
