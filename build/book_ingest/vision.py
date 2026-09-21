"""Lettura dei ritagli difficili con un modello vision su OpenRouter.

Non sostituisce la pipeline: interviene solo dove il riconoscimento locale si
dichiara incerto. I ritagli che riceve sono gia' isolati (una riga di notazione,
un diagramma), quindi il compito e' piccolo e verificabile -- quello che il
modello risponde passa comunque per python-chess, che scarta le mosse illegali
e le posizioni incompatibili.
"""
import base64, json, os, time, urllib.error, urllib.request

URL = 'https://openrouter.ai/api/v1/chat/completions'
# Legge le righe di notazione con le figurine senza sbagliare. Sui DIAGRAMMI
# invece sbanda (confonde le colonne), quindi le posizioni restano affidate al
# riconoscimento locale. Alternativa gratuita ma con tetto di richieste al
# minuto, provata e altrettanto accurata: inclusionai/ling-3.0-flash-vl:free
MODEL = 'google/gemini-3.8-flash'

def ask(png, prompt, model=MODEL, max_tokens=600):
    b64 = base64.b64encode(open(png, 'rb').read()).decode()
    body = {
        'model': model,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
        ]}],
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
        'Authorization': f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        'Content-Type': 'application/json',
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.load(r); break
        except urllib.error.HTTPError as e:
            # i modelli gratuiti hanno un tetto di richieste al minuto
            if e.code in (429, 502, 503) and attempt < 3: time.sleep(6 * (attempt + 1)); continue
            raise
    # il budget di token va tenuto largo: questi modelli spendono token di
    # ragionamento prima di rispondere, e con un tetto basso la risposta torna
    # vuota o troncata a meta' mossa ("Nc" invece di "Nc5")
    msg = out['choices'][0]['message']
    return (msg.get('content') or '').strip()

MOVE_PROMPT = """This image is a single line of chess notation from a printed book.
The piece is shown as a figurine (a small drawing of the piece), not a letter.
Reply with ONLY the move in standard algebraic notation, nothing else.
Use N B R Q K for the pieces, O-O for castling. Keep captures (x), check (+) and
annotation marks (! ?) if present. If the line shows a move number and dots for
Black, ignore them and give just the move. Examples of valid replies: Nf3  Ba4  O-O  Qxb6+  exf5  Rad1
If the image does not contain a chess move (it is prose, a caption, part of a
diagram, or unreadable), reply with exactly: NONE"""

DIAGRAM_PROMPT = """This image is a chess diagram printed in a book. Read the position
square by square and reply with ONLY the board part of the FEN (the piece placement,
8 ranks separated by /, from rank 8 down to rank 1). No move numbers, no side to move,
no castling rights. Example of a valid reply:
r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R"""

def read_move(png, model=MODEL):
    t = ask(png, MOVE_PROMPT, model, 400)
    return t.split()[0].strip('`*.') if t.split() else None

def read_diagram(png, model=MODEL):
    t = ask(png, DIAGRAM_PROMPT, model, 900)
    for tok in t.replace('`', ' ').split():
        if tok.count('/') == 7: return tok
    return None
