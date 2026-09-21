'use strict';
/* A piece set the reader loads from their own device.

   Same rule as the book courses: the app ships only the code, the artwork
   stays on the phone. A commercial set may be used privately by whoever
   owns it, but shipping it inside a public repository would be
   redistribution — so these files go into IndexedDB and never into git.

   app.js asks customPieceSrc() for every piece image it draws; returning
   null falls back to the bundled artwork. */

const PSET_DB = 'openingTrainerPieces';
const PSET_STORE = 'sets';
const PIECE_KEYS = ['wK','wQ','wR','wB','wN','wP','bK','bQ','bR','bB','bN','bP'];

let customPieces = null;      // {wK: dataURL, ...} once loaded

function psetDB(){
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(PSET_DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(PSET_STORE, {keyPath:'id'});
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
function psetTx(mode, run){
  return psetDB().then(db => new Promise((resolve, reject) => {
    const tx = db.transaction(PSET_STORE, mode);
    const out = run(tx.objectStore(PSET_STORE));
    tx.oncomplete = () => resolve(out.result ?? out);
    tx.onerror = () => reject(tx.error);
  }));
}

// app.js hook: 'K' is a white king, 'k' a black one.
function customPieceSrc(ch){
  if(!customPieces) return null;
  const key = (ch === ch.toUpperCase() ? 'w' : 'b') + ch.toUpperCase();
  return customPieces[key] || null;
}

async function loadCustomPieces(){
  let saved = null;
  try { saved = await psetTx('readonly', s => s.get('custom')); }
  catch(e){ return; }                     // private mode: bundled set, no noise
  if(!saved || !saved.map) return;
  customPieces = saved.map;
  repaintPieces();
  // IndexedDB risponde dopo il primo disegno della home, quindi il pannello
  // era gia' stato costruito credendo che il set fosse quello di serie.
  if(document.body.dataset.view === 'home' && typeof go === 'function') go('home');
}

// The set arrives after the first paint, so images already on the board are
// swapped in place rather than rebuilding the view (which would cancel any
// running move animation).
function repaintPieces(){
  for(const piece of document.querySelectorAll('.piece')){
    const ch = piece.dataset.piece;
    const img = piece.querySelector('img');
    if(ch && img) img.src = pieceSrc(ch);
  }
}

/* Filenames differ between sources: "wK.svg", "wk.png", "white-king.png".
   Only the colour and the piece letter matter. */
function pieceKeyOf(name){
  const n = name.toLowerCase().replace(/\.[a-z0-9]+$/, '');
  const colour = /^(w|white)/.test(n) ? 'w' : /^(b|black)/.test(n) ? 'b' : null;
  if(!colour) return null;
  const rest = n.replace(/^(w|b|white|black)[-_ ]?/, '');
  const letter = {k:'K', king:'K', q:'Q', queen:'Q', r:'R', rook:'R',
                  b:'B', bishop:'B', n:'N', knight:'N', p:'P', pawn:'P'}[rest];
  return letter ? colour + letter : null;
}

const readAsDataURL = file => new Promise((resolve, reject) => {
  const fr = new FileReader();
  fr.onload = () => resolve(fr.result);
  fr.onerror = () => reject(fr.error);
  fr.readAsDataURL(file);
});

function importPieceSet(){
  const input = document.createElement('input');
  input.type = 'file'; input.accept = 'image/*'; input.multiple = true;
  input.onchange = async () => {
    const files = [...(input.files || [])];
    if(!files.length) return;
    const map = {}, unknown = [];
    for(const file of files){
      const key = pieceKeyOf(file.name);
      if(!key){ unknown.push(file.name); continue; }
      map[key] = await readAsDataURL(file);
    }
    const missing = PIECE_KEYS.filter(k => !map[k]);
    if(missing.length){
      toast(`Mancano ${missing.length} pezzi: ${missing.join(' ')}`, '');
      return;
    }
    await psetTx('readwrite', s => s.put({id:'custom', map, savedAt: Date.now()}));
    customPieces = map;
    repaintPieces();
    toast(unknown.length ? `Set caricato (${unknown.length} file ignorati).` : 'Set di pezzi caricato.', 'good');
    if(document.body.dataset.view === 'home') go('home');
  };
  input.click();
}

async function clearPieceSet(){
  await psetTx('readwrite', s => s.delete('custom'));
  customPieces = null;
  repaintPieces();
  toast('Tornato al set predefinito.', '');
  if(document.body.dataset.view === 'home') go('home');
}

/* ---------------- settings entry ---------------- */
function renderPieceSetSection(host){
  if(!host) return;
  const box = document.createElement('div');
  box.className = 'pieceset';
  box.innerHTML = `<div class="section-label">PEZZI</div>
    <p class="muted">${customPieces ? 'Stai usando un set tuo, salvato su questo dispositivo.'
      : 'Puoi caricare i tuoi 12 file (wK, wQ, wR, wB, wN, wP e i neri). Restano solo qui.'}</p>`;
  const load = document.createElement('button');
  load.className = 'ghost-btn';
  load.textContent = customPieces ? 'Sostituisci il set' : 'Carica un set di pezzi';
  load.addEventListener('click', importPieceSet);
  box.appendChild(load);
  if(customPieces){
    const reset = document.createElement('button');
    reset.className = 'ghost-btn';
    reset.textContent = 'Torna al set predefinito';
    reset.addEventListener('click', clearPieceSet);
    box.appendChild(reset);
  }
  host.appendChild(box);
}

loadCustomPieces();
