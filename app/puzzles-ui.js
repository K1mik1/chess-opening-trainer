'use strict';

const catalogueCards = () => PUZZLES.filter(c => c.meta.kind === 'catalogue');
const catalogueNeedsReview = c => !!srs(c.id)?.needsReview;
const catalogueLevel = rating => rating < 1000 ? 'base' : rating < 1400 ? 'medio' : 'sfida';
const catalogueLevelName = rating => ({base:'Base',medio:'Intermedio',sfida:'Sfida'})[catalogueLevel(rating)];

const CATALOGUE_REPEAT_GAP = 50;
function catalogueDay(){
  const date=new Date();
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
function migrateCatalogueHistory(){
  let changed=false;
  for(const card of catalogueCards()){
    const record=srs(card.id);
    if(record?.seen && !record.lastPuzzleDay){
      // Historical saves lack the exact completion time/order. Starting a
      // conservative cooldown preserves results without risking immediate repeats.
      record.lastPuzzleDay=catalogueDay();
      record.lastPuzzleSequence=state.profile.catalogueCompletions || 0;
      changed=true;
    }
  }
  if(changed) save();
}
function catalogueRepeatStatus(card){
  if(card.meta?.kind!=='catalogue') return '';
  const record=srs(card.id);
  if(!record?.seen) return '';
  // Older saves have no completion ledger. Preserve them, but conservatively
  // require 50 fresh completions before repeating any of those known positions.
  const completedToday=record.lastPuzzleDay
    ? record.lastPuzzleDay===catalogueDay()
    : record.due-record.interval===today();
  if(completedToday) return 'Già fatto oggi';
  const since=(state.profile.catalogueCompletions || 0)-(record.lastPuzzleSequence || 0);
  return since<CATALOGUE_REPEAT_GAP ? `Pausa: altri ${CATALOGUE_REPEAT_GAP-since} problemi` : '';
}
const catalogueAvailable = card => !catalogueRepeatStatus(card);
function recordCatalogueCompletion(card){
  const sequence=(state.profile.catalogueCompletions || 0)+1;
  state.profile.catalogueCompletions=sequence;
  Object.assign(srs(card.id),{lastPuzzleDay:catalogueDay(),lastPuzzleSequence:sequence});
}
function catalogueCandidates(cards){
  const priority=c=>catalogueNeedsReview(c)||cardState(c.id)==='due'?0:cardState(c.id)==='new'?1:2;
  return cards.filter(catalogueAvailable).sort((a,b)=>priority(a)-priority(b) ||
    Math.abs(a.meta.rating-puzzleRating())-Math.abs(b.meta.rating-puzzleRating()));
}

function puzzlePreferences(){
  const saved=state.settings.puzzlePreferences || {};
  return {
    level:['base','medio','sfida'].includes(saved.level)?saved.level:'all',
    theme:PACKS.some(p=>p.kind==='catalogue' && p.id===saved.theme)?saved.theme:'all'
  };
}
function selectedPuzzleCards(){
  const {level,theme}=puzzlePreferences();
  return catalogueCards().filter(c=>(theme==='all'||c.packId===theme) &&
    (level==='all'||catalogueLevel(c.meta.rating)===level));
}
function startSelectedPuzzles(cards=selectedPuzzleCards(), mixed=true){
  const candidates=catalogueCandidates(cards).slice(0,20);
  if(!candidates.length){
    toast('Nessun problema disponibile con queste impostazioni. Puoi modificarle o tornare più avanti.','');
    return;
  }
  for(let i=candidates.length-1;i>0;i--){ const j=Math.floor(Math.random()*(i+1)); [candidates[i],candidates[j]]=[candidates[j],candidates[i]]; }
  beginSession(candidates.slice(0,10),mixed?'puzzle-mixed':'puzzle-practice',false);
  // Keep the same selection when the initial queue runs out, including its difficulty.
  session.puzzlePool=cards.slice();
}

function renderPuzzleEntry(host){
  const cards = catalogueCards();
  if(!cards.length) return;
  const section = document.createElement('section');
  section.className = 'puzzle-entry';
  const seen = cards.filter(c => srs(c.id)?.seen).length;
  const review = cards.filter(catalogueNeedsReview).length;
  section.innerHTML = `<h2>Problemi di scacchi</h2>
    <p>${cards.length.toLocaleString('it-IT')} posizioni · 8 temi · 3 livelli</p>
    <p class="muted">${seen} affrontati · ${review} da riprovare</p>
    <p id="savedPuzzleSelection" class="muted"></p>
    <div class="puzzle-entry-actions">
      <button class="ghost-btn" data-nav="puzzles">⚙ Impostazioni</button>
      <button class="big-btn small" id="startSavedPuzzles">▶ Inizia problemi</button>
    </div>`;
  const prefs=puzzlePreferences();
  const level={all:'Tutti i livelli',base:'Base · 500–999',medio:'Intermedio · 1000–1399',sfida:'Sfida · 1400–1800'}[prefs.level];
  const theme=PACKS.find(p=>p.id===prefs.theme)?.name || 'Tutti i temi';
  section.querySelector('#savedPuzzleSelection').textContent=`${level} · ${theme}`;
  section.querySelector('#startSavedPuzzles').addEventListener('click',()=>startSelectedPuzzles());
  host.insertBefore(section, host.querySelector('.section-title'));
}

function renderPuzzleCatalogue(){
  const section = document.createElement('section');
  section.className = 'view puzzle-catalogue';
  section.innerHTML = `<button class="back" data-nav="home">‹ Indietro</button>
    <h1>Impostazioni problemi</h1>
    <p class="muted">Scegli difficoltà e tipo di problemi. Le modifiche restano salvate su questo dispositivo, anche quando chiudi la PWA.</p>
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
    <p class="muted puzzle-help">Nel misto il tema resta nascosto fino alla soluzione. Si parte dai problemi vicini al tuo livello stimato; un problema completato non torna oggi e aspetta almeno altri 50 problemi prima di ricomparire.</p>
    <div id="puzzleList" class="cd-lines"></div>
    <button id="puzzleMore" class="ghost-btn" hidden>Mostra altri 100</button>
    <p class="puzzle-source">Fonte: <a href="https://database.lichess.org/#puzzles" target="_blank" rel="noopener">Lichess · CC0</a>. Punteggi Lichess dei problemi, diversi dal punteggio delle partite. Disponibili anche offline.</p>`;
  app.appendChild(section);
  for(const pack of PACKS.filter(p => p.kind==='catalogue')){
    const option = document.createElement('option'); option.value=pack.id; option.textContent=pack.name;
    $('#puzzleTheme').appendChild(option);
  }
  const preferences=puzzlePreferences();
  $('#puzzleTheme').value=preferences.theme;
  $('#puzzleLevel').value=preferences.level;
  const select=selectedPuzzleCards;
  const start=startSelectedPuzzles;
  let visibleCount=100;
  const update = () => {
    const cards=select(), available=cards.filter(catalogueAvailable);
    const review=available.filter(catalogueNeedsReview);
    $('#puzzleCount').textContent=`${cards.length} problemi · ${available.length} disponibili · ${cards.filter(c=>srs(c.id)?.seen).length} affrontati`;
    $('#puzzleReview').textContent=`Ripassa gli errori (${review.length})`;
    $('#puzzleReview').disabled=!review.length;
    $('#puzzleMixed').disabled=$('#puzzlePractice').disabled=!available.length;
    const list=$('#puzzleList'); list.replaceChildren();
    // Keep the enlarged catalogue responsive on iPhone instead of rendering
    // thousands of interactive rows at once.
    for(const card of cards.slice(0,visibleCount)){
      const row=document.createElement('button'); row.className='cd-line puzzle-row';
      const blocked=catalogueRepeatStatus(card);
      const status=blocked || (catalogueNeedsReview(card)?'Da riprovare':cardState(card.id)==='due'?'Ripasso previsto':srs(card.id)?.seen?'Affrontato':'Nuovo');
      row.disabled=!!blocked;
      row.innerHTML=`<span class="cl-top"><b>${card.name}</b><span>${status}</span></span>
        <span class="cl-moves">${card.courseName} · ${catalogueLevelName(card.meta.rating)} · ${card.meta.rating}</span>`;
      row.addEventListener('click',()=>{
        const index=cards.indexOf(card);
        const queue=cards.slice(index).concat(cards.slice(0,index)).filter(catalogueAvailable);
        beginSession(queue, 'puzzle-practice', false);
        session.puzzlePool=cards.slice();
      });
      list.appendChild(row);
    }
    $('#puzzleMore').hidden=visibleCount>=cards.length;
  };
  $('#puzzleMore').addEventListener('click',()=>{visibleCount+=100;update();});
  const resetFilters=()=>{
    state.settings.puzzlePreferences={theme:$('#puzzleTheme').value,level:$('#puzzleLevel').value};
    save(); visibleCount=100; update();
  };
  $('#puzzleTheme').addEventListener('change',resetFilters);
  $('#puzzleLevel').addEventListener('change',resetFilters);
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
  $('#hintBtn').hidden=$('#revealBtn').hidden=true;
  syncPuzzleHistory();
  const controls=document.createElement('div'); controls.id='puzzleCompletion';
  const button=document.createElement('button'); button.className='big-btn small'; button.id='nextPuzzle';
  button.textContent='Prossimo problema →';
  const remainingQueue=()=>session.queue.slice(session.idx+1).filter(catalogueAvailable);
  const continuationPool=()=>catalogueCandidates(session.puzzlePool || catalogueCards());
  const exhausted=!remainingQueue().length && !continuationPool().length;
  if(exhausted){
    button.textContent='Scegli altri problemi';
    const note=document.createElement('p'); note.className='muted';
    note.textContent='Hai esaurito i problemi disponibili in questa selezione. Cambia tema o difficoltà: quelli completati restano in pausa.';
    controls.appendChild(note);
  }
  button.addEventListener('click',()=>{
    const remaining=remainingQueue();
    if(!remaining.length) remaining.push(...continuationPool().slice(0,10));
    if(!remaining.length){ finishSession(); go('puzzles'); return; }
    session.queue.splice(session.idx+1,session.queue.length,...remaining);
    $('.train-actions').insertBefore($('#puzzleHistory'), $('#revealBtn'));
    controls.remove(); next();
  },{once:true});
  const finish=document.createElement('button'); finish.className='ghost-btn'; finish.id='finishPuzzles';
  finish.textContent='Termina sessione';
  finish.addEventListener('click',()=>{controls.remove();finishSession();},{once:true});
  controls.prepend(button);
  controls.appendChild($('#puzzleHistory'));
  controls.appendChild(finish);
  $('.train-info').prepend(controls);
}
