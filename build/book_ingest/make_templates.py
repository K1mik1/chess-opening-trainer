"""Sei modelli, ritagliati dal libro stesso ed etichettati una volta sola.

Gli indici sotto vengono dalla lettura a occhio del foglio dei ritagli
(first_chars.png): e' l'unico passaggio manuale dell'intera pipeline, costa un
minuto per libro e vale per tutte le sue pagine, perche' la figurina e' sempre
lo stesso disegno nello stesso font.
"""
import json
import numpy as np
from PIL import Image
from glyph_tpl import first_char, vec

LABELLED = {
    'N': [2, 3, 7, 16, 17, 24, 26, 29, 31, 34, 51, 62, 63],
    'B': [4, 6, 15, 21, 33, 37, 45, 58],
    'R': [30, 43, 52, 53, 56],
    'Q': [20, 39, 44, 46],
    'K': [48],
    'pawn': [1, 5, 10, 11, 13, 14, 18, 19, 25, 27, 28, 32, 42, 60, 61],
    # la 'x' di cattura: quando il ritaglio comincia di li', la figurina e'
    # rimasta fuori e il simbolo non dice nulla -> nessun vincolo
    'x': [9],
}

rows = [r for r in json.load(open('lines.json')) if any(c.isdigit() for c in r['raw'])]
tiles = []
for r in rows:
    img = Image.open(f"cols/p{r['page']}_c{r['col']}.png")
    t = first_char(img, r['box'])
    tiles.append(t if (t and t.width >= 6 and t.height >= 6) else None)
tiles = [t for t in tiles if t is not None]

templates = {}
for label, idxs in LABELLED.items():
    vs = [vec(tiles[i]) for i in idxs if i < len(tiles)]
    templates[label] = [v.tolist() for v in vs]
json.dump(templates, open('templates.json', 'w'))
print({k: len(v) for k, v in templates.items()})
