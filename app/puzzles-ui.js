'use strict';

const catalogueCards = () => PUZZLES.filter(c => c.meta.kind === 'catalogue');
const catalogueNeedsReview = c => !!srs(c.id)?.needsReview;
const catalogueLevel = rating => rating < 1000 ? 'base' : rating < 1400 ? 'medio' : 'sfida';
const catalogueLevelName = rating => ({base:'Base',medio:'Intermedio',sfida:'Sfida'})[catalogueLevel(rating)];

function renderPuzzleEntry(host){
  const cards = catalogueCards();
  if(!cards.length) return;
  const section = document.createElement('section');
  section.className = 'puzzle-entry';
  const seen = cards.filter(c => srs(c.id)?.seen).length;
  const review = cards.filter(catalogueNeedsReview).length;
  section.innerHTML = `<h2>Problemi di scacchi</h2>
    <p>200 posizioni · 8 temi · 3 livelli</p>
    <p class="muted">${seen} affrontati · ${review} da riprovare</p>
    <button class="big-btn small" data-nav="puzzles">♟ Scegli i problemi</button>`;
  host.insertBefore(section, host.querySelector('.section-title'));
}

function renderPuzzleCatalogue(){
  const section = document.createElement('section');
  section.className = 'view puzzle-catalogue';
  section.innerHTML = `<button class="back" data-nav="home">‹ Indietro</button>
    <h1>Problemi di scacchi</h1>
    <p class="muted">Scegli un tema oppure allenati senza indizi con una sessione mista.</p>
    <div class="puzzle-filters">
      <label>Tema<select id="puzzleTheme"><option value="all">Tutti i temi</option></select></label>
      <label>Difficoltà<select id="puzzleLevel"><option value="all">Tutti i livelli</option>
        <option value="base">Base · 500–999</option><option value="medio">Intermedio · 1000–1399</option>
        <option value="sfida">Sfida · 1400–1800</option></select></label>
    </div>
    <p id="puzzleCount" class="muted" aria-live="polite"></p>
    <div class="puzzle-actions">
      <button id="puzzleMixed" class="big-btn small">▶ 10 problemi misti</button>
      <button id="puzzlePractice" class="ghost-btn">Allena la selezione</button>
      <button id="puzzleReview" class="ghost-btn">Ripassa gli errori</button>
    </div>
    <p class="muted puzzle-help">Nel misto il tema resta nascosto fino alla soluzione. Si parte dai problemi vicini al tuo livello stimato; quelli già affrontati tornano quando è ora di ripassarli.</p>
    <div id="puzzleList" class="cd-lines"></div>
    <p class="puzzle-source">Fonte: <a href="https://database.lichess.org/#puzzles" target="_blank" rel="noopener">Lichess · CC0</a>. Punteggi Lichess dei problemi, diversi dal punteggio delle partite. Disponibili anche offline.</p>`;
  app.appendChild(section);
  for(const pack of PACKS.filter(p => p.kind==='catalogue')){
    const option = document.createElement('option'); option.value=pack.id; option.textContent=pack.name;
    $('#puzzleTheme').appendChild(option);
  }
  const select = () => catalogueCards().filter(c =>
    ($('#puzzleTheme').value==='all' || c.packId===$('#puzzleTheme').value) &&
    ($('#puzzleLevel').value==='all' || catalogueLevel(c.meta.rating)===$('#puzzleLevel').value));
  const start = (cards, mixed) => {
    if(!cards.length){ toast('Nessun problema da ripassare in questa selezione.',''); return; }
    // Unseen/due positions take priority; shuffle a nearby pool to avoid repeating
    // the same opening sequence every time a session is interrupted.
    const priority = c => catalogueNeedsReview(c) || cardState(c.id)==='due' ? 0 : cardState(c.id)==='new' ? 1 : 2;
    const candidates = cards.slice().sort((a,b) => priority(a)-priority(b) ||
      Math.abs(a.meta.rating-puzzleRating())-Math.abs(b.meta.rating-puzzleRating())).slice(0,20);
    for(let i=candidates.length-1;i>0;i--){ const j=Math.floor(Math.random()*(i+1)); [candidates[i],candidates[j]]=[candidates[j],candidates[i]]; }
    beginSession(candidates.slice(0,10), mixed?'puzzle-mixed':'puzzle-practice', false);
    session.puzzlePool=cards.slice();
  };
  const update = () => {
    const cards=select(), review=cards.filter(catalogueNeedsReview);
    $('#puzzleCount').textContent=`${cards.length} problemi · ${cards.filter(c=>srs(c.id)?.seen).length} affrontati · ${review.length} da riprovare`;
    $('#puzzleReview').textContent=`Ripassa gli errori (${review.length})`;
    $('#puzzleReview').disabled=!review.length;
    const list=$('#puzzleList'); list.replaceChildren();
    for(const card of cards){
      const row=document.createElement('button'); row.className='cd-line puzzle-row';
      const status=catalogueNeedsReview(card)?'Da riprovare':cardState(card.id)==='due'?'Ripasso previsto':srs(card.id)?.seen?'Affrontato':'Nuovo';
      row.innerHTML=`<span class="cl-top"><b>${card.name}</b><span>${status}</span></span>
        <span class="cl-moves">${card.courseName} · ${catalogueLevelName(card.meta.rating)} · ${card.meta.rating}</span>`;
      row.addEventListener('click',()=>{
        const index=cards.indexOf(card);
        // Keep browsing order and active filters when continuing from a row.
        beginSession(cards.slice(index).concat(cards.slice(0,index)), 'puzzle-practice', false);
        session.puzzlePool=cards.slice();
      });
      list.appendChild(row);
    }
  };
  $('#puzzleTheme').addEventListener('change',update);
  $('#puzzleLevel').addEventListener('change',update);
  $('#puzzleMixed').addEventListener('click',()=>start(select(),true));
  $('#puzzlePractice').addEventListener('click',()=>start(select(),false));
  $('#puzzleReview').addEventListener('click',()=>start(select().filter(catalogueNeedsReview),true));
  update();
}

function showPuzzleResult(card, mistakes, next){
  const panel=$('#planCard'); panel.hidden=false;
  $('#planGoal').textContent=mistakes?'Soluzione completata — da riprovare':'Risolto senza aiuti!';
  $('#planText').textContent=packById(card.packId).blurb;
  $('#planIdea').textContent=card.courseName;
  $('#planAvoid').textContent='Guarda sempre anche la risposta migliore dell’avversario.';
  const source=$('#planSource'); source.href=card.meta.sourceUrl; source.textContent='Rivedi il problema su Lichess ↗';
  $('#hintBtn').disabled=$('#revealBtn').disabled=true;
  $('.train-actions').style.display='none';
  const controls=document.createElement('div'); controls.id='puzzleCompletion';
  const button=document.createElement('button'); button.className='big-btn small'; button.id='nextPuzzle';
  button.textContent='Prossimo problema →';
  button.addEventListener('click',()=>{
    if(session.idx+1>=session.queue.length){
      // Finishing a batch must not force a trip back through the catalogue.
      const pool=session.puzzlePool?.length>1 ? session.puzzlePool : catalogueCards();
      const candidates=pool.filter(c=>c.id!==card.id).sort((a,b)=>
        Number(!!srs(a.id)?.seen)-Number(!!srs(b.id)?.seen) ||
        Math.abs(a.meta.rating-puzzleRating())-Math.abs(b.meta.rating-puzzleRating()));
      session.queue.push(...candidates.slice(0,10));
    }
    controls.remove(); next();
  },{once:true});
  const finish=document.createElement('button'); finish.className='ghost-btn'; finish.id='finishPuzzles';
  finish.textContent='Termina sessione';
  finish.addEventListener('click',()=>{controls.remove();finishSession();},{once:true});
  controls.append(button,finish);
  $('.train-info').prepend(controls);
}
