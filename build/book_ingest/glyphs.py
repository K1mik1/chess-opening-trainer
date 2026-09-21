"""Ritaglia il simbolo del pezzo da ogni riga-mossa.

Nel libro la figurina e' il segno piu' "pesante" della riga: piu' alta e piu'
piena delle cifre e delle lettere di coordinata. Quindi non serve capire dove
finisce il numero e dove comincia la casa -- basta segmentare la riga in blocchi
di inchiostro separati da spazi bianchi e prendere il blocco con l'area maggiore.
"""
import json, sys
import numpy as np
from PIL import Image

def blobs(arr, gap=6):
    """Gruppi di colonne con inchiostro, separati da almeno `gap` colonne bianche."""
    ink = (arr < 150)
    cols = ink.sum(axis=0)
    groups, start, blank = [], None, 0
    for x, v in enumerate(cols):
        if v > 0:
            if start is None: start = x
            blank = 0
        elif start is not None:
            blank += 1
            if blank >= gap:
                groups.append((start, x - blank)); start = None
    if start is not None: groups.append((start, len(cols) - 1))
    return [(a, b) for a, b in groups if b - a >= 3]

def glyph_of(img, box, pad=8):
    l, t, r, b = box
    crop = img.crop((max(0, l - pad), max(0, t - pad), r + pad, b + pad))
    arr = np.asarray(crop.convert('L'))
    gs = blobs(arr)
    if not gs: return None, None
    # La mossa sta sempre in fondo alla riga (a sinistra ci sono numero e
    # puntini), quindi si parte dall'ultimo blocco. La figurina a volte resta
    # staccata dalla casa: se il blocco precedente e' li' accanto fa parte
    # della mossa e va incluso, altrimenti "Ba4" si riduce a "a4" e l'alfiere
    # sparisce dalla lettura.
    a, b = gs[-1]
    if len(gs) >= 2:
        pa, pb = gs[-2]
        if a - pb < crop.height * 0.55 and pb - pa < crop.height * 1.2:
            a = pa
    return crop.crop((max(0, a - 2), 0, b + 2, crop.height)), (a, b)

if __name__ == '__main__':
    rows = json.load(open('lines.json'))
    picks = [r for r in rows if len(r['raw'].split()) <= 4 and any(c.isdigit() for c in r['raw'])][:24]
    tiles, labels = [], []
    for r in picks:
        img = Image.open(f"cols/p{r['page']}_c{r['col']}.png")
        g, _ = glyph_of(img, r['box'])
        if g is None: continue
        tiles.append(g.resize((64, 64))); labels.append(r['raw'])
    W = 8
    sheet = Image.new('L', (W * 70, ((len(tiles) + W - 1) // W) * 80), 255)
    for i, t in enumerate(tiles):
        sheet.paste(t.convert('L'), ((i % W) * 70 + 3, (i // W) * 80 + 3))
    sheet.save('glyph_sheet.png')
    for i, l in enumerate(labels): print(i, repr(l))
