"""Isola il PRIMO carattere del blocco-mossa: se e' una figurina la classifichiamo,
se e' una lettera di coordinata la mossa e' di pedone. Sei forme per tutto il
libro, quindi bastano sei modelli ritagliati dal libro stesso."""
import json, sys
import numpy as np
from PIL import Image
from glyphs import glyph_of, blobs

def first_char(img, box):
    blk, _ = glyph_of(img, box)
    if blk is None: return None
    arr = np.asarray(blk.convert('L'))
    gs = blobs(arr, gap=2)          # dentro il blocco i caratteri sono vicini
    if not gs: return None
    a, b = gs[0]
    rows = np.where((arr[:, a:b] < 150).any(axis=1))[0]
    if len(rows) == 0: return None
    return blk.crop((a, rows[0], b, rows[-1] + 1))

def vec(tile, n=24):
    t = tile.convert('L').resize((n, n), Image.LANCZOS)
    v = 1.0 - np.asarray(t, dtype=float) / 255.0
    return (v / (np.linalg.norm(v) + 1e-9)).ravel()

if __name__ == '__main__':
    rows = [r for r in json.load(open('lines.json')) if any(c.isdigit() for c in r['raw'])]
    tiles, meta = [], []
    for r in rows:
        img = Image.open(f"cols/p{r['page']}_c{r['col']}.png")
        t = first_char(img, r['box'])
        if t is None or t.width < 6 or t.height < 6: continue
        tiles.append(t); meta.append(r['raw'])
    W = 10
    sheet = Image.new('L', (W * 46, ((len(tiles) + W - 1)//W) * 52), 255)
    for i, t in enumerate(tiles):
        sheet.paste(t.convert('L').resize((40, 40)), ((i % W) * 46 + 3, (i // W) * 52 + 3))
    sheet.save('first_chars.png')
    json.dump(meta, open('first_chars_meta.json', 'w'))
    print(f"{len(tiles)} ritagli -> first_chars.png")
    for i in range(0, len(meta), 10):
        print(i, ' | '.join(f"{j}:{meta[j][:9]!r}" for j in range(i, min(i+10, len(meta)))))
