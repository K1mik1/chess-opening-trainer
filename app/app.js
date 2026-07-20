/* =====================================================================
   Opening Trainer  --  offline, single-file app logic
   Data comes from window.REPERTOIRE (generated, DB-verified book moves).
   No chess engine needed at runtime: every position is precomputed, and a
   user move is "correct" iff it matches the one book move for that position.
   ===================================================================== */
'use strict';

const STARTFEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const GLYPHS = {k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'};
const MATURE = 21;            // interval (days) at which a line counts "mastered"
const $  = (s,r=document)=>r.querySelector(s);
const $$ = (s,r=document)=>[...r.querySelectorAll(s)];
const COURSES = window.REPERTOIRE;

/* ---------------- board themes (traditional, chess.com / Lichess style) ------ */
const THEMES = [
  {id:'green',  name:'Tournament Green', light:'#eeeed2', dark:'#769656'},
  {id:'walnut', name:'Walnut Parlor',    light:'#f0d9b5', dark:'#b58863'},
  {id:'blue',   name:'Tournament Hall',  light:'#dee3e6', dark:'#8ca2ad'},
];
function applyTheme(id){
  if(!THEMES.some(t=>t.id===id)) id='green';
  document.body.classList.remove(...THEMES.map(t=>'theme-'+t.id));
  document.body.classList.add('theme-'+id);
}

/* ---------------- date helpers (local day index) ---------------- */
function today(){ const d=new Date(); d.setHours(0,0,0,0); return Math.round(d.getTime()/864e5); }

/* ---------------- persistent state ---------------- */
const SKEY = 'openingTrainer.v1';
const DEFAULTS = () => ({
  v:1,
  profile:{xp:0, streak:0, bestStreak:0, lastDay:null, totalMoves:0,
           sessionsDone:0, perfectSessions:0},
  cards:{},                 // cardId -> {seen,ease,interval,due,reps,lapses,lastGrade}
  badges:{},
  settings:{muted:false, newPerDay:4, maxSession:14, theme:'green'},
  lastSummary:null,
});
let state = load();
function load(){
  try{ const s=JSON.parse(localStorage.getItem(SKEY)); if(s&&s.v===1){
        const d=DEFAULTS(); return {...d,...s, profile:{...d.profile,...s.profile},
          settings:{...d.settings,...s.settings}, cards:s.cards||{}, badges:s.badges||{}}; }
  }catch(e){}
  return DEFAULTS();
}
function save(){ try{ localStorage.setItem(SKEY, JSON.stringify(state)); }catch(e){ /* storage blocked: keep running in-memory */ } }

/* ---------------- card model (enumerate every variation) ---------------- */
let CARDS=[];                 // flat list
const CARD_BY_ID={};
const CARDS_BY_COURSE={};
(function enumerate(){
  for(const c of COURSES){
    CARDS_BY_COURSE[c.id]=[];
    let li=0;
    (function dfs(node,path){
      const ch=node.children;
      if(!ch.length){
        const card={id:`${c.id}#${li++}`, courseId:c.id, color:c.color,
          courseName:c.name, name:node.name||c.name, edges:path,
          myMoves:path.filter(e=>e.mine).length};
        CARDS.push(card); CARD_BY_ID[card.id]=card; CARDS_BY_COURSE[c.id].push(card);
        return;
      }
      for(const e of ch) dfs(e.node, path.concat(e));
    })(c.tree, []);
  }
})();
const courseById = id => COURSES.find(c=>c.id===id);

/* ---------------- spaced repetition (SM-2 lite) ---------------- */
function srs(id){ return state.cards[id]; }
function cardState(id){
  const s=srs(id);
  if(!s||!s.seen) return 'new';
  if(s.due<=today()) return 'due';
  return s.interval>=MATURE ? 'mature' : 'learning';
}
function gradeFromMistakes(m){ return m===0?'easy': m===1?'good': m<=3?'hard':'again'; }
function schedule(id, grade){
  const t=today();
  let s=srs(id) || {seen:false, ease:2.5, interval:0, due:t, reps:0, lapses:0};
  switch(grade){
    case 'again': s.lapses++; s.reps=0; s.ease=Math.max(1.3,s.ease-0.2); s.interval=0; break;
    case 'hard':  s.reps++;   s.ease=Math.max(1.3,s.ease-0.15);
                  s.interval = s.interval? Math.max(1,Math.round(s.interval*1.2)) : 1; break;
    case 'good':  s.reps++;   s.interval = s.reps===1?1 : s.reps===2?3 : Math.round((s.interval||1)*s.ease); break;
    case 'easy':  s.reps++;   s.ease+=0.05;
                  s.interval = s.reps===1?2 : Math.round((s.interval||1)*s.ease*1.3); break;
  }
  s.interval=Math.min(s.interval,365);
  s.seen=true; s.due=t+s.interval; s.lastGrade=grade;
  state.cards[id]=s; return s;
}

/* ---------------- aggregate stats ---------------- */
// Graduated mastery for a single card: 0 when never seen, ~0.38 once introduced,
// climbing to 1.0 as the review interval reaches MATURE. This makes progress
// visible immediately instead of only after a line survives ~3 weeks of reviews.
function cardStrength(id){
  const s=srs(id);
  if(!s||!s.seen) return 0;
  return Math.min(1, 0.35 + 0.65*(s.interval/MATURE));
}
function courseProgress(courseId){
  const list=CARDS_BY_COURSE[courseId];
  let mature=0, due=0, seen=0, strength=0;
  for(const c of list){ const st=cardState(c.id);
    if(st==='mature') mature++; if(st==='due') due++; if(st!=='new') seen++;
    strength+=cardStrength(c.id); }
  return {total:list.length, mature, due, seen,
          pct:Math.round(strength/list.length*100)};
}
function overallMastery(){
  let strength=0; for(const c of CARDS) strength+=cardStrength(c.id);
  return Math.round(strength/CARDS.length*100);
}
function dueCount(){ let d=0; for(const c of CARDS) if(cardState(c.id)==='due') d++; return d; }
function newAvailable(){ let n=0; for(const c of CARDS) if(cardState(c.id)==='new') n++; return n; }
function stars(pct){ return pct>=90?3 : pct>=60?2 : pct>=25?1 : 0; }

/* ---------------- backlog catch-up (load balancing) ----------------
   After a break, overdue reviews pile up. Rather than dumping them all as
   "due today", we cap the daily review load and spread the excess across the
   following days — the same load-balancing modern SRS (Anki/FSRS) uses.
   Ordering is most-fragile-first (shortest interval, then most overdue), so
   the lines you're likeliest to have forgotten come back first; well-learned
   overdue lines are pushed furthest out (a small extra delay is harmless for
   a memory that already survived the gap). No review is dropped — only when
   it appears is redistributed, and the schedule self-corrects once you catch up. */
function rebalanceBacklog(){
  const t=today();
  const cap=Math.max(1, state.settings.maxSession||14);
  const overdue=[];
  const load={};            // absolute day index -> count of on-time/future reviews
  for(const c of CARDS){ const s=srs(c.id); if(!s||!s.seen) continue;
    if(s.due<t) overdue.push(c.id);
    else load[s.due]=(load[s.due]||0)+1;
  }
  // If today's load is already comfortable, leave the schedule untouched.
  if(overdue.length + (load[t]||0) <= cap) return;
  overdue.sort((a,b)=>{ const sa=srs(a), sb=srs(b);
    return (sa.interval-sb.interval) || (sa.due-sb.due); });
  let day=t;
  for(const id of overdue){
    while((load[day]||0)>=cap) day++;      // find the earliest day with spare capacity
    srs(id).due=day; load[day]=(load[day]||0)+1;
  }
  save();
}

/* ---------------- level / xp ---------------- */
function levelInfo(xp){ let lvl=1, need=100, rem=xp;
  while(rem>=need){ rem-=need; lvl++; need=100+(lvl-1)*50; } return {lvl,into:rem,need}; }
function refreshTopbar(){
  const li=levelInfo(state.profile.xp);
  $('#levelVal').textContent=li.lvl;
  $('#streakVal').textContent=state.profile.streak;
  $('#xpfill').style.width=(li.into/li.need*100)+'%';
  $('#xpText').textContent=`${li.into}/${li.need} XP`;
  $('#muteBtn').textContent=state.settings.muted?'🔇':'🔊';
}

/* ===================================================================
   AUDIO  (tiny WebAudio blips, fully offline)
   =================================================================== */
let actx=null;
function tone(freq,dur,type='sine',vol=.15,when=0){
  if(state.settings.muted) return;
  try{ actx=actx||new (window.AudioContext||window.webkitAudioContext)();
    const o=actx.createOscillator(), g=actx.createGain();
    o.type=type; o.frequency.value=freq; o.connect(g); g.connect(actx.destination);
    const t=actx.currentTime+when; g.gain.setValueAtTime(vol,t);
    g.gain.exponentialRampToValueAtTime(.0001,t+dur);
    o.start(t); o.stop(t+dur);
  }catch(e){}
}
const SND={
  move:()=>tone(320,.07,'triangle',.12),
  good:()=>{tone(660,.08,'sine',.16);tone(990,.1,'sine',.14,.07);},
  bad: ()=>tone(150,.18,'sawtooth',.14),
  win: ()=>{[523,659,784,1046].forEach((f,i)=>tone(f,.15,'triangle',.16,i*.09));},
  level:()=>{[392,523,659,784,1046].forEach((f,i)=>tone(f,.18,'sine',.16,i*.08));},
};

/* ===================================================================
   ROUTING / VIEWS
   =================================================================== */
const app=$('#app');
function tpl(id){ return document.importNode($('#'+id).content,true); }
function clearView(){ app.innerHTML=''; }
function go(view, arg){
  clearView();
  if(view==='home') renderHome();
  else if(view==='course') renderCourse(arg);
  document.body.dataset.view=view;
}
document.addEventListener('click', e=>{
  const nav=e.target.closest('[data-nav]'); if(nav){ go(nav.dataset.nav); }
});
$('#muteBtn').addEventListener('click',()=>{
  state.settings.muted=!state.settings.muted; save(); refreshTopbar();
  if(!state.settings.muted) SND.good();
});

/* ---------------- HOME ---------------- */
function renderHome(){
  app.appendChild(tpl('tpl-home'));
  const p=state.profile;
  const hr=new Date().getHours();
  $('#greeting').textContent =
    (hr<12?'Good morning':hr<18?'Good afternoon':'Good evening')+' — ready to train?';
  const mastery=overallMastery();
  $('#subgreeting').textContent =
    `Level ${levelInfo(p.xp).lvl} · ${p.streak}-day streak · ${mastery}% of your repertoire mastered`;

  // mastery ring
  const C=2*Math.PI*52;
  $('#ringFg').style.strokeDashoffset = C*(1-mastery/100);
  $('#ringPct').textContent = mastery+'%';
  $('.ring-label small').textContent='mastered';

  // due summary
  const due=dueCount(), nw=Math.min(newAvailable(), state.settings.newPerDay);
  const nextNew=CARDS.find(c=>cardState(c.id)==='new');
  const ds=$('#dueSummary');
  if(due+nw>0) ds.innerHTML = `<b>${due}</b> line${due===1?'':'s'} due for review` +
      (nw? ` · <b>${nw}</b> new to learn` : '') + ` — about ${estMinutes(due+nw)} min` +
      (nw&&nextNew? `<br><span style="font-size:.92em">next up: <b>${courseById(nextNew.courseId).name}</b></span>` : '');
  else if(newAvailable()>0) ds.innerHTML=`No reviews due. Tap to learn <b>${Math.min(newAvailable(),state.settings.newPerDay)}</b> new line(s).`;
  else ds.innerHTML='🎉 All caught up! Nothing due today — come back tomorrow, or drill any opening below.';

  $('#startBtn').addEventListener('click', startDaily);

  // course cards, grouped by difficulty tier (the learning curve)
  const TIER_LABEL={1:'Beginner — start here',2:'Intermediate',3:'Advanced'};
  const host=$('#courseGrid');
  host.classList.remove('course-grid');           // becomes a plain container
  const buildCard=c=>{
    const pr=courseProgress(c.id);
    const card=document.createElement('div'); card.className='course-card';
    card.innerHTML=`
      <div class="cc-top">
        <span class="tag ${c.color}">${c.color==='white'?'▲ White':'▼ Black'}</span>
        ${pr.due?`<span class="due-pill">${pr.due} due</span>`:`<span class="due-pill none">${pr.seen<pr.total?'learn':'✓'}</span>`}
      </div>
      <h3>${c.name}</h3>
      <div class="cc-bar"><div style="width:${pr.pct}%"></div></div>
      <div class="cc-meta"><span class="stars">${'★'.repeat(stars(pr.pct))}${'☆'.repeat(3-stars(pr.pct))}</span>
        <span>${pr.mature}/${pr.total} mastered</span></div>`;
    card.addEventListener('click',()=>go('course',c.id));
    return card;
  };
  const tiers=[...new Set(COURSES.map(c=>c.tier||1))].sort((a,b)=>a-b);
  for(const t of tiers){
    const group=document.createElement('div'); group.className='tier-group';
    group.innerHTML=`<div class="tier-head"><span class="tier-chip t${t}">${TIER_LABEL[t]||('Tier '+t)}</span></div>`;
    const grid=document.createElement('div'); grid.className='course-grid';
    for(const c of COURSES.filter(x=>(x.tier||1)===t)) grid.appendChild(buildCard(c));
    group.appendChild(grid); host.appendChild(group);
  }
  renderBadges($('#badgeRow'));

  // board theme picker
  const cur=state.settings.theme||'green';
  const themeWrap=document.createElement('div');
  themeWrap.style.cssText='margin:24px 0 4px;text-align:center';
  themeWrap.innerHTML='<div style="color:var(--muted);font-size:.8rem;margin-bottom:9px;'+
    'text-transform:uppercase;letter-spacing:.08em">Board theme</div>';
  const sw=document.createElement('div'); sw.className='theme-swatches';
  for(const t of THEMES){
    const b=document.createElement('button');
    b.className='swatch'+(cur===t.id?' active':''); b.title=t.name;
    b.innerHTML=`<span class="sw-board">`+
      `<i style="background:${t.light}"></i><i style="background:${t.dark}"></i>`+
      `<i style="background:${t.dark}"></i><i style="background:${t.light}"></i></span>${t.name}`;
    b.addEventListener('click',()=>{
      state.settings.theme=t.id; save(); applyTheme(t.id);
      $$('.swatch',sw).forEach(x=>x.classList.remove('active')); b.classList.add('active');
    });
    sw.appendChild(b);
  }
  themeWrap.appendChild(sw);
  app.querySelector('.home').appendChild(themeWrap);

  // small footer: daily new-line setting + reset
  const foot=document.createElement('div');
  foot.style.cssText='margin-top:26px;text-align:center;color:var(--muted);font-size:.8rem';
  const selCss='background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:3px 6px';
  const rpdOpts=[...new Set([8,10,14,18,25,state.settings.maxSession])].sort((a,b)=>a-b);
  foot.innerHTML=`New lines per day:
    <select id="npd" style="${selCss}">
      ${[2,3,4,5,8].map(n=>`<option ${state.settings.newPerDay===n?'selected':''}>${n}</option>`).join('')}
    </select>
    &nbsp;·&nbsp; Reviews per day:
    <select id="rpd" style="${selCss}" title="Caps how many reviews pile up per day — extras spread to later days">
      ${rpdOpts.map(n=>`<option ${state.settings.maxSession===n?'selected':''}>${n}</option>`).join('')}
    </select>
    &nbsp;·&nbsp; <a id="resetLink" href="#" style="color:var(--muted)">Reset all progress</a>`;
  app.querySelector('.home').appendChild(foot);
  $('#npd').addEventListener('change',e=>{ state.settings.newPerDay=+e.target.value; save(); go('home'); });
  $('#rpd').addEventListener('change',e=>{ state.settings.maxSession=+e.target.value; save(); rebalanceBacklog(); go('home'); });
  $('#resetLink').addEventListener('click',e=>{ e.preventDefault();
    if(confirm('Reset all progress, XP, streak and review schedule? This cannot be undone.')){
      state=DEFAULTS(); save(); applyTheme(state.settings.theme); refreshTopbar(); go('home'); toast('Progress reset.',''); }
  });
}
function estMinutes(lines){ return Math.max(1, Math.round(lines*0.7)); }

/* ---------------- COURSE DETAIL ---------------- */
function renderCourse(courseId){
  app.appendChild(tpl('tpl-course'));
  const c=courseById(courseId);
  $('#cdName').textContent=c.name;
  $('#cdSummary').textContent=c.summary;
  $('#cdDrill').addEventListener('click',()=>startCourse(courseId,false));
  $('#cdLearn').addEventListener('click',()=>startCourse(courseId,true));
  const wrap=$('#cdLines');
  CARDS_BY_COURSE[courseId].forEach((card,i)=>{
    const st=cardState(card.id);
    const lbl={new:'New',due:'Review due',learning:'Learning',mature:'Mastered'}[st];
    const sans=card.edges.map(e=>e.san).join(' ');
    const row=document.createElement('div'); row.className='cd-line';
    row.innerHTML=`<div class="cl-top"><span class="cl-name">${i===0?'★ ':''}${shortName(card.name,c.name)}</span>
        <span class="cl-state ${st}">${lbl}</span></div>
      <div class="cl-moves">${numbered(card.edges)}</div>`;
    row.addEventListener('click',()=>startLine(card,false));
    wrap.appendChild(row);
  });
}
function shortName(name,courseName){
  if(name.startsWith(courseName)) { const r=name.slice(courseName.length).replace(/^[:,\s]+/,''); return r||'Main line'; }
  return name;
}
function numbered(edges){
  // ply 0 is always White's move; number every White move "n."
  let str='';
  edges.forEach((e,i)=>{ str += (i%2===0 ? `${i/2+1}.${e.san} ` : `${e.san} `); });
  return str.trim();
}

/* ---------------- badges ---------------- */
const BADGES=[
  {id:'first',  ico:'🎯', name:'First Steps',   test:p=>p.sessionsDone>=1},
  {id:'streak7',ico:'🔥', name:'Week Warrior',  test:p=>p.bestStreak>=7},
  {id:'streak30',ico:'⚡',name:'Unstoppable',   test:p=>p.bestStreak>=30},
  {id:'century',ico:'💯', name:'Centurion',     test:p=>p.totalMoves>=100},
  {id:'perfect',ico:'✨', name:'Flawless',      test:p=>p.perfectSessions>=1},
  {id:'scholar',ico:'🎓', name:'Opening Expert',test:()=>COURSES.some(c=>courseProgress(c.id).pct===100)},
  {id:'polyglot',ico:'🌍',name:'All-Rounder',   test:()=>COURSES.every(c=>courseProgress(c.id).mature>=1)},
  {id:'grinder',ico:'🏆', name:'Dedicated',     test:p=>p.sessionsDone>=30},
];
function checkBadges(){
  for(const b of BADGES){ if(!state.badges[b.id] && b.test(state.profile)){
    state.badges[b.id]=true; toast(`${b.ico} Badge unlocked: ${b.name}`,'gold'); confetti(); SND.win();
  }}
  save();
}
function renderBadges(host){
  host.innerHTML='';
  for(const b of BADGES){ const got=state.badges[b.id];
    const el=document.createElement('div'); el.className='badge'+(got?'':' locked');
    el.innerHTML=`<span class="b-ico">${b.ico}</span>${b.name}`;
    host.appendChild(el);
  }
}

/* ===================================================================
   TRAINER ENGINE
   =================================================================== */
let board, boardWrap, overlay, session=null, play=null, engineBusy=false, selected=null, whiteBottom=true;

function buildDailyQueue(){
  const t=today();
  const reviews=CARDS.filter(c=>cardState(c.id)==='due')
                     .sort((a,b)=>srs(a.id).due-srs(b.id).due)
                     .slice(0,state.settings.maxSession);
  let budget=Math.max(0, state.settings.maxSession-reviews.length);
  budget=Math.min(budget, state.settings.newPerDay);
  const news=CARDS.filter(c=>cardState(c.id)==='new').slice(0,budget);
  return reviews.concat(news);
}
function startDaily(){
  const q=buildDailyQueue();
  if(!q.length){ toast('All caught up! Try drilling an opening 👇','good'); return; }
  beginSession(q,'daily',false);
}
function startCourse(courseId, learn){
  const q=CARDS_BY_COURSE[courseId].slice();
  beginSession(q, learn?'learn':'course', learn);
}
function startLine(card, learn){ beginSession([card], learn?'learn':'line', learn); }

function beginSession(queue, mode, learn){
  session={queue, idx:0, mode, learn, results:[], xpGained:0,
           movesPlayed:0, firstTry:0, requeues:0};
  clearView(); app.appendChild(tpl('tpl-train'));
  board=$('#board'); boardWrap=$('.board-wrap'); overlay=$('#boardOverlay');
  $('#hintBtn').addEventListener('click', onHint);
  $('#revealBtn').addEventListener('click', onReveal);
  board.addEventListener('click', onBoardClick);
  document.body.dataset.view='train';
  startCard(session.queue[0]);
}

function startCard(card){
  play={card, color:card.color, edges:card.edges, fen:STARTFEN, step:0,
        wrong:0, hintMoves:0, wrongThisMove:0, hintThisMove:false, requeued:false};
  whiteBottom = card.color==='white';
  renderBoard(STARTFEN, whiteBottom);
  $('#lineName').textContent = `${card.courseName} — ${shortName(card.name,card.courseName)}`;
  $('#moveList').innerHTML='';
  updateSessBar();
  $('#hintBtn').disabled=$('#revealBtn').disabled=false;
  selected=null;
  setTimeout(processStep, session.learn?500:350);
}
function updateSessBar(){
  $('#sessBarFill').style.width=(session.idx/session.queue.length*100)+'%';
  $('#sessCount').textContent=`${session.idx+1}/${session.queue.length}`;
}

function processStep(){
  if(play.step>=play.edges.length){ return finishCard(); }
  const edge=play.edges[play.step];
  if(edge.mine && !session.learn){
    play.awaiting=true; selected=null;
    setPrompt(`Your move as ${play.color}. What's the book move?`, '');
  } else {
    play.awaiting=false;
    if(session.learn && edge.mine) setPrompt(`Book move: ${edge.san}`,'good');
    else setPrompt('', '');
    engineBusy=true;
    setTimeout(()=>playEdge(edge, ()=>{ play.step++; processStep(); }), session.learn?750:430);
  }
}

function onBoardClick(e){
  if(!play || !play.awaiting || engineBusy || session.learn) return;
  const sq=e.target.closest('.sq'); if(!sq) return;
  const square=sq.dataset.square;
  const map=parseFEN(play.fen);
  const myUpper = play.color==='white';
  const here=map[square];
  const isMine = here && (here===here.toUpperCase())===myUpper;

  if(selected===null){
    if(isMine){ selected=square; markSel(square); }
    return;
  }
  if(square===selected){ selected=null; clearSel(); return; }
  if(isMine){ selected=square; markSel(square); return; }   // reselect own piece
  // attempt move selected -> square
  const edge=play.edges[play.step];
  clearSel();
  const from=selected; selected=null;
  if(from===edge.from && square===edge.to){
    play.awaiting=false;
    goodFeedback(edge);
    engineBusy=true;
    playEdge(edge, ()=>{
      // tally this move
      session.movesPlayed++; state.profile.totalMoves++;
      if(play.wrongThisMove===0 && !play.hintThisMove) session.firstTry++;
      addXp(play.hintThisMove?4:10, edge.to);
      play.wrongThisMove=0; play.hintThisMove=false;
      play.step++; processStep();
    });
  } else {
    play.wrong++; play.wrongThisMove++;
    badFeedback(from, square);
    setPrompt(`Not the book move here — try again.`, 'bad');
    if(play.wrongThisMove>=2) highlightHint(edge.from, null);   // nudge after 2 misses
  }
}

function onHint(){
  if(!play||!play.awaiting||session.learn) return;
  const edge=play.edges[play.step];
  highlightHint(edge.from, null);
  if(!play.hintThisMove){ play.hintThisMove=true; }
  setPrompt('Hint: move the highlighted piece.', '');
}
function onReveal(){
  if(!play||!play.awaiting||engineBusy||session.learn) return;
  const edge=play.edges[play.step];
  play.hintThisMove=true; play.hintMoves++;
  highlightHint(edge.from, edge.to);
  setPrompt(`The book move is ${edge.san}.`, '');
  play.awaiting=false; selected=null; clearSel();
  engineBusy=true;
  setTimeout(()=>playEdge(edge, ()=>{
    session.movesPlayed++; state.profile.totalMoves++;
    play.wrongThisMove=0; play.hintThisMove=false;
    play.step++; processStep();
  }), 900);
}

function finishCard(){
  const mistakes = play.wrong + play.hintMoves;
  const grade = session.learn ? null : gradeFromMistakes(mistakes);
  if(session.learn){
    // Learn mode doesn't grade, but completing a lesson should register the
    // line as introduced (so it shows progress and gets scheduled for review).
    const s=srs(play.card.id);
    if(!s||!s.seen) schedule(play.card.id, 'good');
  }
  if(grade){
    schedule(play.card.id, grade);
    session.results.push({id:play.card.id, grade, mistakes});
    if(grade==='easy'){ addXp(25); toast('Perfect line! +25 XP','good'); miniConfetti(); }
    else if(grade==='good'){ addXp(10); }
    // re-queue lapses once for immediate relearn (daily/course only)
    if(grade==='again' && session.mode!=='line' && session.requeues<6 && !play.requeued){
      session.queue.push(play.card); session.requeues++; play.requeued=true;
    }
  }
  save();
  session.idx++;
  if(session.idx>=session.queue.length) return finishSession();
  setTimeout(()=>startCard(session.queue[session.idx]), 500);
  updateSessBar();
}

function finishSession(){
  $('#sessBarFill').style.width='100%';
  const p=state.profile;
  const completed = session.results.length;
  if(!session.learn && completed>0){
    p.sessionsDone++;
    // streak
    const t=today();
    if(p.lastDay!==t){
      p.streak = (p.lastDay===t-1)? p.streak+1 : 1;
      p.lastDay=t; p.bestStreak=Math.max(p.bestStreak||0, p.streak);
    }
    const allPerfect = session.results.every(r=>r.grade==='easy');
    if(allPerfect) p.perfectSessions++;
  }
  state.lastSummary={
    when:today(), lines:completed,
    acc: session.movesPlayed? Math.round(session.firstTry/session.movesPlayed*100):100,
    xp: session.xpGained, streak:p.streak,
  };
  save(); refreshTopbar(); checkBadges();
  showSummary();
}

function showSummary(){
  app.appendChild(tpl('tpl-summary'));
  const s=state.lastSummary;
  if(session.learn){ $('#sumTitle').textContent='Lesson complete 📖'; }
  $('#sumLines').textContent=s.lines;
  $('#sumAcc').textContent=s.acc+'%';
  $('#sumXp').textContent='+'+s.xp;
  $('#sumStreak').textContent=s.streak;
  const due=dueCount();
  $('#sumNext').textContent = due? `${due} more line(s) still due — keep going!`
      : `Next reviews unlock as your lines come due. See you tomorrow! 🔥`;
  if(s.acc>=90 && s.lines>0){ confetti(); SND.win(); }
}

/* ---------------- feedback helpers ---------------- */
function setPrompt(text, cls){
  const el=$('#turnPrompt'); el.textContent=text; el.className='turn-prompt '+(cls||'');
}
function goodFeedback(edge){ flashSquare(edge.to,'good-flash'); flashOverlay('✓','good'); SND.good(); setPrompt('Correct!','good'); }
function badFeedback(from,to){ flashSquare(to||from,'bad-flash'); flashOverlay('✗','bad'); SND.bad(); }
function flashOverlay(txt,cls){ overlay.textContent=txt; overlay.className='board-overlay show '+cls;
  setTimeout(()=>overlay.className='board-overlay', 550); }

/* ===================================================================
   BOARD RENDERING + ANIMATION
   =================================================================== */
function parseFEN(fen){
  const rows=fen.split(' ')[0].split('/'); const map={};
  for(let r=0;r<8;r++){ let f=0;
    for(const ch of rows[r]){
      if(/\d/.test(ch)) f+=+ch;
      else { map['abcdefgh'[f]+(8-r)]=ch; f++; }
    }
  } return map;
}
function pieceHTML(ch){
  const color = (ch===ch.toUpperCase())?'white':'black';
  return `<span class="piece ${color}">${GLYPHS[ch.toLowerCase()]}</span>`;
}
function renderBoard(fen, whiteBot){
  const map=parseFEN(fen);
  const files = whiteBot? ['a','b','c','d','e','f','g','h'] : ['h','g','f','e','d','c','b','a'];
  const ranks = whiteBot? [8,7,6,5,4,3,2,1] : [1,2,3,4,5,6,7,8];
  let html='';
  ranks.forEach((rank,ri)=>{
    files.forEach((file,fi)=>{
      const fileIdx='abcdefgh'.indexOf(file);
      const dark=(fileIdx+(rank-1))%2===0;
      const sqn=file+rank;
      const pc=map[sqn]?pieceHTML(map[sqn]):'';
      const fileLbl = (ri===7)?`<span class="coord file">${file}</span>`:'';
      const rankLbl = (fi===0)?`<span class="coord rank">${rank}</span>`:'';
      html+=`<div class="sq ${dark?'dk':'lt'}" data-square="${sqn}">${rankLbl}${fileLbl}${pc}</div>`;
    });
  });
  board.innerHTML=html;
}
function sqEl(square){ return board.querySelector(`[data-square="${square}"]`); }
function markSel(square){ clearSel(); sqEl(square)?.classList.add('sel'); }
function clearSel(){ $$('.sq.sel',board).forEach(s=>s.classList.remove('sel')); }
function clearHints(){ $$('.hintfrom,.hintto',board).forEach(s=>s.classList.remove('hintfrom','hintto')); }
function highlightHint(from,to){ clearHints(); sqEl(from)?.classList.add('hintfrom'); if(to) sqEl(to)?.classList.add('hintto'); }
function flashSquare(square,cls){ const el=sqEl(square); if(!el)return; el.classList.add(cls); setTimeout(()=>el.classList.remove(cls),520); }
function highlightLast(from,to){ $$('.lastfrom,.lastto',board).forEach(s=>s.classList.remove('lastfrom','lastto'));
  sqEl(from)?.classList.add('lastfrom'); sqEl(to)?.classList.add('lastto'); }

function sqCenter(square){
  const el=sqEl(square), br=boardWrap.getBoundingClientRect(), r=el.getBoundingClientRect();
  return {x:r.left-br.left+r.width/2, y:r.top-br.top+r.height/2};
}
function flyPiece(from,to,ch,dur,cb){
  const a=sqCenter(from), b=sqCenter(to);
  const color=(ch===ch.toUpperCase())?'white':'black';
  const fly=document.createElement('div');
  fly.className='flyer piece '+color; fly.textContent=GLYPHS[ch.toLowerCase()];
  fly.style.left=a.x+'px'; fly.style.top=a.y+'px'; fly.style.transform='translate(-50%,-50%)';
  boardWrap.appendChild(fly);
  requestAnimationFrame(()=>{ fly.style.transform=`translate(calc(-50% + ${b.x-a.x}px), calc(-50% + ${b.y-a.y}px))`; });
  setTimeout(()=>{ fly.remove(); cb&&cb(); }, dur+30);
}
function playEdge(edge, cb){
  const map=parseFEN(play.fen);
  const ch=map[edge.from];
  // hide moving source piece during the flight
  const srcPiece=sqEl(edge.from)?.querySelector('.piece'); if(srcPiece) srcPiece.remove();
  clearHints();
  // animate rook too on castling
  if(edge.castle){ const rch=map[edge.castle.from];
    const rkPiece=sqEl(edge.castle.from)?.querySelector('.piece'); if(rkPiece) rkPiece.remove();
    if(rch) flyPiece(edge.castle.from, edge.castle.to, rch, 220, null);
  }
  const finish=()=>{
    play.fen=edge.node.fen;
    renderBoard(play.fen, whiteBottom);
    highlightLast(edge.from, edge.to);
    addMoveChip(edge);
    if(!edge.mine) SND.move();
    engineBusy=false; cb&&cb();
  };
  if(ch) flyPiece(edge.from, edge.to, ch, 220, finish); else finish();
}
function addMoveChip(edge){
  const ml=$('#moveList');
  const chip=document.createElement('span');
  chip.className='mv'+(edge.mine?' me':'');
  chip.textContent=edge.san;
  ml.appendChild(chip);
}

/* ===================================================================
   XP popups, toasts, confetti
   =================================================================== */
function addXp(n, atSquare){
  state.profile.xp+=n; session.xpGained+=n;
  const before=levelInfo(state.profile.xp - n).lvl;
  const after=levelInfo(state.profile.xp).lvl;
  refreshTopbar();
  if(atSquare && board){ const c=sqCenter(atSquare);
    const pop=document.createElement('div'); pop.className='xp-pop';
    pop.textContent='+'+n; pop.style.left=c.x+'px'; pop.style.top=c.y+'px';
    pop.style.transform='translate(-50%,-50%)'; boardWrap.appendChild(pop);
    setTimeout(()=>pop.remove(),1000);
  }
  if(after>before){ toast(`⬆️ Level ${after}!`,'gold'); SND.level(); confetti(); }
}
let toastTimer;
function toast(msg, cls){
  const host=$('#toastHost');
  const t=document.createElement('div'); t.className='toast '+(cls||''); t.textContent=msg;
  host.appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; t.style.transition='opacity .4s'; setTimeout(()=>t.remove(),400); }, 2200);
}

/* confetti */
const cvs=$('#confetti'); const cx=cvs && cvs.getContext && cvs.getContext('2d');
function confetti(){ burst(140); } function miniConfetti(){ burst(60); }
function burst(n){
  if(!cx) return;                       // no 2d canvas (e.g. headless) -> skip gracefully
  cvs.style.display='block'; resizeCvs();
  const cs=getComputedStyle(document.body);
  const colors=['--accent','--accent2','--good','--gold','--bad']
    .map(v=>cs.getPropertyValue(v).trim()||'#888');
  const parts=[];
  for(let i=0;i<n;i++) parts.push({x:cvs.width/2+(Math.random()-.5)*200, y:cvs.height*0.25,
    vx:(Math.random()-.5)*9, vy:Math.random()*-8-2, g:0.28,
    s:6+Math.random()*7, c:colors[i%colors.length], r:Math.random()*6, vr:(Math.random()-.5)*.4});
  let frames=0;
  (function anim(){ cx.clearRect(0,0,cvs.width,cvs.height); frames++;
    parts.forEach(p=>{ p.vy+=p.g; p.x+=p.vx; p.y+=p.vy; p.r+=p.vr;
      cx.save(); cx.translate(p.x,p.y); cx.rotate(p.r); cx.fillStyle=p.c;
      cx.fillRect(-p.s/2,-p.s/2,p.s,p.s*0.6); cx.restore(); });
    if(frames<110) requestAnimationFrame(anim);
    else { cx.clearRect(0,0,cvs.width,cvs.height); cvs.style.display='none'; }
  })();
}
function resizeCvs(){ cvs.width=innerWidth; cvs.height=innerHeight; }
addEventListener('resize',()=>{ if(cvs.style.display==='block') resizeCvs(); });

/* ===================================================================
   INIT
   =================================================================== */
function rolloverStreakCheck(){
  // if user missed a day, streak is recomputed on next completed session.
  // here we just display the stored streak (don't reset until a session).
}
applyTheme(state.settings.theme);
refreshTopbar();
rolloverStreakCheck();
rebalanceBacklog();
go('home');
