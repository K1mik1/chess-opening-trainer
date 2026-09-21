'use strict';
/* Annotated games taken from chess books.

   The courses themselves are NOT shipped with the app: a book's commentary
   belongs to its author, so the file is imported from the device and kept in
   IndexedDB, where it stays on that phone. Only this reader is public code.

   The board, its animations and the piece images are reused from app.js as
   they are — a game viewer has no reason to grow a second renderer. */

const BOOKS_DB = 'openingTrainerBooks';
const BOOKS_STORE = 'courses';

function booksDB(){
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(BOOKS_DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(BOOKS_STORE, {keyPath:'id'});
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
function booksTx(mode, run){
  return booksDB().then(db => new Promise((resolve, reject) => {
    const tx = db.transaction(BOOKS_STORE, mode);
    const out = run(tx.objectStore(BOOKS_STORE));
    tx.oncomplete = () => resolve(out.result ?? out);
    tx.onerror = () => reject(tx.error);
  }));
}
const booksAll    = () => booksTx('readonly',  s => s.getAll());
const booksGet    = id => booksTx('readonly',  s => s.get(id));
const booksPut    = c  => booksTx('readwrite', s => s.put(c));
const booksDelete = id => booksTx('readwrite', s => s.delete(id));

// Where the reader is in each game, so reopening a book resumes instead of
// restarting. Lives with the rest of the progress, not in the course file.
function bookMark(gameId, ply){
  state.books = state.books || {};
  if(ply === undefined) return state.books[gameId] || 0;
  state.books[gameId] = ply; save();
}

/* ---------------- home entry ---------------- */
async function renderBooksSection(host){
  if(!host) return;
  let courses = [];
  try { courses = await booksAll(); } catch(e){ return; }   // private mode: skip quietly
  const section = document.createElement('section');
  section.className = 'books-entry';
  const games = courses.reduce((n,c) => n + c.games.length, 0);
  section.innerHTML = `<h2>Libri</h2>
    <p class="muted">${courses.length ? `${courses.length} corso/i · ${games} partite commentate` :
      'Nessun libro caricato. Importa un corso creato dai tuoi PDF.'}</p>
    <button class="big-btn small" data-nav="books">📖 Apri i libri</button>`;
  // In cima, accanto ai problemi: in fondo alla home finiva sotto badge, temi
  // e impostazioni, dove nessuno la trova senza scorrere l'intera pagina.
  const anchor = host.querySelector('.section-title');
  if(anchor) host.insertBefore(section, anchor); else host.appendChild(section);
}

/* ---------------- course list ---------------- */
async function renderBooks(){
  const section = document.createElement('section');
  section.className = 'view books';
  section.innerHTML = `<button class="back" data-nav="home">‹ Indietro</button>
    <h1>Libri</h1>
    <p class="muted">Partite commentate estratte dai tuoi libri. Restano su questo dispositivo.</p>
    <div class="books-actions"><button id="bookImport" class="big-btn small">⬇ Importa un corso</button></div>
    <div id="bookList" class="cd-lines"></div>`;
  app.appendChild(section);
  $('#bookImport').addEventListener('click', importCourse);
  await refreshBookList();
}

async function refreshBookList(){
  const host = $('#bookList'); if(!host) return;
  const courses = await booksAll();
  if(!courses.length){ host.innerHTML = '<p class="muted">Ancora niente qui.</p>'; return; }
  host.innerHTML = '';
  for(const course of courses){
    const box = document.createElement('div');
    box.className = 'book-course';
    box.innerHTML = `<h2>${course.title}</h2><p class="muted">${course.book || ''}</p>`;
    for(const game of course.games){
      const done = bookMark(game.id), total = game.moves.length;
      const row = document.createElement('button');
      row.className = 'cd-line';
      // A game rebuilt with gaps is flagged here rather than silently trusted.
      const warn = game.flags && (game.flags.resync || game.flags.skipped > 12)
        ? ' <span class="muted">· da rivedere</span>' : '';
      row.innerHTML = `<b>${game.players}</b><span class="muted">${game.event || ''}</span>
        <span class="muted">${total} mosse${done ? ` · sei a ${Math.ceil(done/2)}` : ''}${warn}</span>`;
      row.addEventListener('click', () => go('bookgame', game.id));
      box.appendChild(row);
    }
    const del = document.createElement('button');
    del.className = 'ghost-btn';
    del.textContent = 'Rimuovi questo corso';
    del.addEventListener('click', async () => {
      if(!confirm(`Rimuovere "${course.title}" da questo dispositivo?`)) return;
      await booksDelete(course.id); await refreshBookList();
    });
    box.appendChild(del);
    host.appendChild(box);
  }
}

function importCourse(){
  const input = document.createElement('input');
  input.type = 'file'; input.accept = 'application/json,.json';
  input.onchange = async () => {
    const file = input.files && input.files[0]; if(!file) return;
    let course;
    try { course = JSON.parse(await file.text()); }
    catch(e){ toast('Quel file non è JSON valido.',''); return; }
    if(!course || !course.id || !Array.isArray(course.games)){
      toast('Non sembra un corso del trainer.',''); return;
    }
    await booksPut(course);
    toast(`Importato: ${course.title} (${course.games.length} partite).`,'good');
    await refreshBookList();
  };
  input.click();
}

/* ---------------- one game ---------------- */
async function renderBookGame(gameId){
  const courses = await booksAll();
  let course = null, game = null;
  for(const c of courses){
    const g = c.games.find(x => x.id === gameId);
    if(g){ course = c; game = g; break; }
  }
  if(!game) return go('books');

  const section = document.createElement('section');
  section.className = 'view book-game';
  section.innerHTML = `<div class="train-head">
      <button class="back" data-nav="books">‹ Libri</button>
      <div id="bookCount" class="muted"></div>
    </div>
    <div class="board-wrap">
      <div id="board" class="board"></div>
      <div id="boardOverlay" class="board-overlay"></div>
    </div>
    <div class="train-info">
      <div class="line-name">${game.players}</div>
      <div class="line-sub">${game.event || course.book || ''}</div>
      <div class="moves" id="bookMove"></div>
      <p id="bookComment"></p>
      <div class="train-actions book-actions">
        <button id="bookNext" class="big-btn small">Mossa successiva ›</button>
        <button id="bookPrev" class="ghost-btn">‹ Indietro</button>
        <button id="bookRestart" class="ghost-btn">Da capo</button>
      </div>
    </div>`;
  app.appendChild(section);
  board = $('#board'); boardWrap = $('.board-wrap'); overlay = $('#boardOverlay');
  whiteBottom = true;

  let ply = Math.min(bookMark(game.id), game.moves.length);
  const show = (target, animate) => {
    const prev = ply;
    ply = Math.max(0, Math.min(target, game.moves.length));
    const move = ply ? game.moves[ply-1] : null;
    // Stepping forward one move animates the piece the way the trainer does;
    // jumping or going back just redraws, which is what the eye expects.
    if(animate && move && ply === prev + 1 && prev > 0){
      const from = game.moves[prev-1];
      renderBoard(from.fen, whiteBottom);
      const flight = animatePiece(move.from, move.to);
      // animatePiece hands back {piece, to, animation}: the piece has to be
      // moved into its destination square and the animation cleared, exactly
      // as playEdge does, or the board keeps a transformed ghost. Castling
      // only animates the king; the final redraw puts the rook in place.
      const settle = () => {
        if(!board || !document.body.contains(board)) return;
        if(flight){
          const target = board.querySelector(`[data-square="${flight.to}"]`);
          if(target){ target.querySelector('.piece')?.remove(); target.appendChild(flight.piece); }
          flight.animation.cancel();
          flight.piece.classList.remove('moving');
          boardAnimations.delete(flight.animation);
        }
        renderBoard(move.fen, whiteBottom);
        highlightLast(move.from, move.to);
      };
      if(flight) flight.animation.finished.then(settle, settle); else settle();
    } else {
      renderBoard(move ? move.fen : STARTFEN, whiteBottom);
      if(move) highlightLast(move.from, move.to);
    }
    $('#bookCount').textContent = `${ply} / ${game.moves.length}`;
    $('#bookMove').innerHTML = move
      ? `<b>${move.n}${move.side === 'w' ? '.' : '…'} ${move.san}</b>`
      : '<span class="muted">Posizione iniziale</span>';
    $('#bookComment').textContent = move ? (move.comment || '') : '';
    $('#bookNext').disabled = ply >= game.moves.length;
    $('#bookPrev').disabled = ply === 0;
    bookMark(game.id, ply);
  };

  $('#bookNext').addEventListener('click', () => show(ply + 1, true));
  $('#bookPrev').addEventListener('click', () => show(ply - 1, false));
  $('#bookRestart').addEventListener('click', () => show(0, false));
  section.addEventListener('keydown', e => {
    if(e.key === 'ArrowRight') show(ply + 1, true);
    if(e.key === 'ArrowLeft') show(ply - 1, false);
  });
  section.tabIndex = 0; section.focus();
  show(ply, false);
}
