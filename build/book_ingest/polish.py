"""Ripulisce e traduce i commenti del libro.

Il testo esce dall'OCR con tre difetti ricorrenti: le figurine diventano
lettere a caso dentro le varianti citate ("2...We7" per "2...Qe7"), le parole
a fine riga restano spezzate ("straight- forward") e i punti elenco del libro
diventano @ o #. Qui si correggono e si traduce, dando al modello la mossa e
la posizione come contesto: senza, non puo' sapere che "We7" era una donna.

Il modello traduce, NON riscrive: un commento inventato in un corso di scacchi
e' peggio di un commento assente, quindi le risposte troppo lunghe rispetto
all'originale vengono segnalate invece che accettate in silenzio.
"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
import vision                                  # riusa il client OpenRouter

CACHE = 'polish_cache.json'
MODEL = 'google/gemini-3.8-flash'

PROMPT = """Questo è il commento a una mossa di scacchi, estratto via OCR da un libro
inglese. La mossa commentata è {move} e la posizione dopo la mossa è {fen}.

Il testo ha errori tipici dell'OCR:
- i simboli dei pezzi nelle varianti citate sono diventati lettere a caso
  (& o £ = alfiere, W = donna, A o D = cavallo, E o H = torre, S = re), e le
  cifre si confondono con le lettere (eS = e5, l = 1)
- le parole a fine riga sono spezzate ("straight- forward")
- i punti elenco del libro appaiono come @ # ♦

Riscrivi il commento IN ITALIANO, correggendo questi errori. Regole:
- traduci fedelmente: non aggiungere idee, valutazioni o mosse che non ci sono
- lascia la notazione in forma inglese (Nf3, Bb5, Qe7, O-O), correggendola dove
  l'OCR l'ha storpiata, usando la posizione come guida
- se una parte è incomprensibile, ometti quella parte invece di inventarla
- rispondi SOLO con il testo italiano finale: niente virgolette, niente note,
  niente alternative, niente ragionamento ad alta voce

Testo:
{text}"""

THINKING = re.compile(r'(\bNo,|\bo forse\b|\bse dice\b|\bcioè\?|\?\s*No\b)', re.I)

def acceptable(out, text):
    """Una traduzione si accetta solo se somiglia a una traduzione.

    Il modello, se resta a corto di token, tronca a meta' frase; una volta ha
    perfino restituito il proprio ragionamento ("20.Qxg8+? No, lasciamo...")
    al posto del testo. Una versione inglese corretta e' meglio di una
    italiana inventata, quindi qui si rifiuta invece di accettare al buio.
    """
    if not out: return 'risposta vuota'
    ratio = len(out) / max(1, len(text))
    if ratio < 0.75: return f'troppo corta ({ratio:.2f}x): troncata o incompleta'
    if ratio > 1.7: return f'troppo lunga ({ratio:.2f}x): potrebbe aver ricamato'
    if THINKING.search(out): return 'contiene ragionamento invece della traduzione'
    # Solo se l'originale era una frase compiuta: diversi commenti escono
    # gia' troncati dall'OCR, e li' una traduzione troncata e' fedele.
    if text.rstrip()[-1] in '.!?' and out.rstrip()[-1] not in '.!?»"\'':
        return 'finisce a meta\' frase'
    return None

def polish_one(item):
    key, move, fen, text = item
    prompt = PROMPT.format(move=move, fen=fen, text=text)
    last = None
    for attempt in range(2):
        try:
            out = vision.ask_text(prompt, MODEL)
        except Exception as e:
            return key, None, f'errore: {e}'
        problem = acceptable(out, text)
        if not problem: return key, out.strip(), None
        last = problem
    return key, None, last

def main(path):
    games = json.load(open(path))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = []
    for g in games:
        for u in g['units']:
            c = (u.get('comment') or '').strip()
            if len(c) < 25: continue
            key = f"{g['page']}:{u['n']}{u['side']}"
            if key in cache: continue
            move = f"{u['n']}{'.' if u['side']=='w' else '...'}{u['san']}"
            todo.append((key, move, u.get('fen_before',''), c))
    print(f'commenti da tradurre: {len(todo)}')
    flags = []
    if todo:
        with ThreadPoolExecutor(6) as ex:
            for n, (key, out, flag) in enumerate(ex.map(polish_one, todo), 1):
                if out: cache[key] = out
                if flag: flags.append((key, flag))
                if n % 25 == 0:
                    print(f'  {n}/{len(todo)}', flush=True); json.dump(cache, open(CACHE,'w'), ensure_ascii=False)
        json.dump(cache, open(CACHE,'w'), ensure_ascii=False)
    for g in games:
        for u in g['units']:
            key = f"{g['page']}:{u['n']}{u['side']}"
            if key in cache: u['comment_it'] = cache[key]
    json.dump(games, open(path,'w'), ensure_ascii=False, indent=1)
    print(f'tradotti in cache: {len(cache)} | da rivedere: {len(flags)}')
    for k, f in flags[:10]: print('  !', k, f)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'chapter1.json')
