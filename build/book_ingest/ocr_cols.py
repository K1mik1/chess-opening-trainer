"""OCR colonna per colonna: tesseract su tutta la pagina rimescola l'ordine
quando incontra i diagrammi. Tagliando prima le due colonne, l'ordine di lettura
resta quello del libro e ogni commento resta attaccato alla sua mossa."""
import os, subprocess, sys
import numpy as np, pymupdf
from PIL import Image

PDF = '/Users/furiomariot/Desktop/Chess The Art of Logical Thinking From the First Move to the Last (Neil McDonald).pdf'
OUT = 'cols'; os.makedirs(OUT, exist_ok=True)

def column_split(arr):
    """Trova il corridoio bianco centrale (gutter) via proiezione verticale."""
    ink = (arr < 160).sum(axis=0)
    h, w = arr.shape
    mid = slice(int(w*0.40), int(w*0.60))
    band = ink[mid]
    return int(w*0.40) + int(np.argmin(band))

doc = pymupdf.open(PDF)
for page in range(int(sys.argv[1]), int(sys.argv[2])):
    pm = doc[page].get_pixmap(dpi=300)
    img = Image.frombytes('RGB', (pm.width, pm.height), pm.samples).convert('L')
    arr = np.asarray(img)
    cut = column_split(arr)
    top, bot = int(pm.height*0.055), int(pm.height*0.97)   # via intestazione e numero di pagina
    for i, box in enumerate([(0, top, cut, bot), (cut, top, pm.width, bot)]):
        p = f'{OUT}/p{page}_c{i}.png'
        img.crop(box).save(p)
        txt = subprocess.run(['tesseract', p, '-', '--psm', '4'],
                             capture_output=True, text=True).stdout
        open(f'{OUT}/p{page}_c{i}.txt', 'w').write(txt)
    print('pagina', page, 'gutter a x=', cut)
