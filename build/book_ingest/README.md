# Ingest dei libri di scacchi

Estrae partite annotate da un PDF scansionato e produce un corso che l'app
importa da file (`app/books.js`), senza passare dal repo.

    python ocr_cols.py  9 36        # taglia le colonne e le passa a tesseract
    python ocr_lines.py 9 36        # isola le righe-mossa e ne salva i ritagli
    python book_ingest.py 9 36      # legge le mosse e ricostruisce le partite
    python polish.py chapter1.json  # corregge l'OCR e traduce in italiano
    python make_course.py           # scrive il file che l'app importa

Richiede `python-chess`, `pymupdf`, `pillow`, `tesseract` e una chiave
`OPENROUTER_API_KEY` per la lettura delle righe.

## Come decide cosa è una mossa

L'OCR su queste scansioni sbaglia spesso: le figurine (♘ al posto di N) escono
come caratteri a caso e i numeri perdono cifre ("13" letto "3"). Ogni filtro
basato su quel testo ha finito per buttare via mosse vere, quindi le decisioni
si prendono altrove:

- **layout** — una mossa giocata è isolata tipograficamente (spazio sopra e
  sotto); una variante citata vive dentro il paragrafo;
- **legalità** — una partita si apre sulla prima mossa legale dalla posizione
  iniziale, e nessuna lettura entra se non è legale nella posizione corrente;
- **diagrammi** — le posizioni stampate fanno da riscontro: i dodici modelli
  dei pezzi si imparano dal primo diagramma, la cui posizione è già nota.

## Sui commenti

`polish.py` passa ogni commento a un modello con la mossa e la posizione come
contesto: senza, non può sapere che `2...We7` era `2...Qe7`. Traduce e non
riscrive, e una risposta entra nel corso solo se ha lunghezza plausibile, non
contiene tracce di ragionamento e non finisce a metà frase — tre controlli
nati da altrettanti errori veri, incluso un caso in cui il modello ha
restituito il proprio ragionamento al posto del testo. Quando la traduzione
viene rifiutata resta l'inglese ripulito: meglio in inglese che inventato.

Il numero di mossa è un indizio, non una chiave: se la mossa è legale e il
numero è appena più avanti, il contatore si riallinea e la risincronizzazione
viene contata: una partita che ne accumula molte va rivista.
