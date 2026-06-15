/* End-to-end UI test using jsdom: loads the real index.html + app.js, then
   drives the trainer by dispatching real clicks on board squares.
   Verifies: home renders, a session starts, a wrong move is rejected, correct
   moves advance the line, opponent replies auto-play, XP accrues, and the
   session-summary modal appears. Run: node build/test_ui.js  */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const APP = path.join(__dirname, '..', 'app');
const html = fs.readFileSync(path.join(APP, 'index.html'), 'utf8');
const url = 'file://' + path.join(APP, 'index.html').replace(/\\/g, '/');

const dom = new JSDOM(html, {
  url, runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
});
const { window } = dom;
const delay = ms => new Promise(r => setTimeout(r, ms));
const ev = (typeof window.eval === 'function') ? s => window.eval(s) : null;

let failed = 0;
const ok  = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) failed++; };

function clickSquare(sq) {
  const el = window.document.querySelector(`[data-square="${sq}"]`);
  if (!el) { failed++; console.log('  ✗ no square ' + sq); return; }
  el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
}
const peek = () => JSON.parse(ev(`JSON.stringify({
  step: (typeof play!=='undefined'&&play)?play.step:-1,
  total:(typeof play!=='undefined'&&play)?play.edges.length:-1,
  awaiting:(typeof play!=='undefined'&&play)?!!play.awaiting:false,
  wrong:(typeof play!=='undefined'&&play)?play.wrong:0,
  edge:(typeof play!=='undefined'&&play&&play.edges[play.step])?
    {from:play.edges[play.step].from,to:play.edges[play.step].to,mine:play.edges[play.step].mine,san:play.edges[play.step].san}:null,
  xp:(typeof state!=='undefined')?state.profile.xp:0,
  inSummary: !!document.getElementById('summaryModal')
})`));

// Play a whole line by clicking book moves. Returns stats.
async function playLine(cardId, { injectWrong } = {}) {
  ev(`startLine(CARD_BY_ID['${cardId}'], false)`);
  await delay(140);
  const xp0 = peek().xp;
  let guard = 0, didWrong = false, myMoves = 0, wrongRejected = null;
  while (guard++ < 600) {
    const st = peek();
    if (st.inSummary) break;
    if (st.step >= st.total && st.total >= 0) { await delay(120); continue; }
    if (!st.awaiting || !st.edge || !st.edge.mine) { await delay(50); continue; }

    if (injectWrong && !didWrong) {
      didWrong = true;
      const wrongTo = ev(`(function(){var m=parseFEN(play.fen);` +
        `for(var f of ['a3','h3','a6','h6','b3','g3','b6','g6','c4','f4','e3','d3']){` +
        `if(!m[f]&&f!==play.edges[play.step].to)return f;}return 'a3';})()`);
      clickSquare(st.edge.from); clickSquare(wrongTo);
      await delay(40);
      const after = peek();
      wrongRejected = (after.step === st.step && after.wrong >= 1 && after.awaiting);
    }
    clickSquare(st.edge.from);
    clickSquare(st.edge.to);
    myMoves++;
    await delay(110);
  }
  const acc = window.document.getElementById('sumAcc');
  const finalFen = ev('play.fen');
  // dismiss summary -> home
  const done = window.document.querySelector('#summaryModal [data-nav="home"]');
  if (done) done.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await delay(60);
  return { myMoves, xpGained: peek().xp - xp0, acc: acc && acc.textContent,
           completed: peek().inSummary === false, wrongRejected, finalFen };
}

async function main() {
  await new Promise(res => window.addEventListener('load', res));
  await delay(100);

  ok(!!window.document.querySelector('.view.home'), 'home view rendered');
  ok(window.document.querySelectorAll('.course-card').length === 12, '12 course cards shown');
  ok(window.document.querySelectorAll('.tier-group').length >= 2, 'courses grouped into difficulty tiers');
  ok(ev('typeof startLine') === 'function', 'app globals reachable for driving');
  // daily scheduler introduces the FIRST course (curriculum order) first
  ok(ev(`buildDailyQueue()[0].courseId`) === ev(`CARDS.find(c=>cardState(c.id)==='new').courseId`),
     'daily queue starts from the first unseen course (learning curve)');
  ok(ev(`COURSES[0].tier`) === 1, 'first course is a Beginner-tier course');

  // themes
  const swatches = window.document.querySelectorAll('.swatch');
  ok(swatches.length === 3, '3 board themes available');
  ok(window.document.body.classList.contains('theme-green'), 'default traditional theme (green) applied');
  swatches[1].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await delay(20);
  ok(window.document.body.classList.contains('theme-walnut') &&
     !window.document.body.classList.contains('theme-green'), 'switching theme swaps body class');
  ok(ev('state.settings.theme') === 'walnut', 'theme choice persisted to state');

  // 1) Caro-Kann line #0 with a deliberate wrong move
  const r1 = await playLine('caro_kann#0', { injectWrong: true });
  ok(r1.wrongRejected, 'wrong move rejected (line did not advance, marked wrong)');
  ok(r1.myMoves >= 4, `Caro line completed (${r1.myMoves} of my moves)`);
  ok(r1.xpGained > 0, `XP increased on Caro line (+${r1.xpGained})`);
  ok(/%$/.test(r1.acc || ''), 'summary shows accuracy: ' + r1.acc);
  ok(window.document.querySelector('.view.home'), 'returned home after summary');

  // 2) Deepest line in the whole repertoire (long line, all-correct -> perfect)
  const deepId = ev(`Object.keys(CARD_BY_ID).reduce((a,b)=>CARD_BY_ID[b].myMoves>CARD_BY_ID[a].myMoves?b:a)`);
  const r2 = await playLine(deepId);
  ok(r2.myMoves >= 10, `deepest line (${deepId}) played ${r2.myMoves} moves`);
  ok(/^(100|9\d)%$/.test(r2.acc), 'all-correct deep line scored high accuracy: ' + r2.acc);

  // 3) Italian line #0 -- I (White) castle; verify the king ends on g1
  const r3 = await playLine('italian#0');
  const kStr = JSON.stringify(r3.finalFen);
  ok(r3.finalFen.split(' ')[0].split('/')[7].includes('K'), 'Italian: White king on back rank after play');
  // king specifically on g1 (kingside castled): rank 1 is last field segment
  const rank1 = r3.finalFen.split(' ')[0].split('/')[7];
  ok((function(){let f=0;for(const c of rank1){if(/\d/.test(c))f+=+c;else{if(c==='K'&&'abcdefgh'[f]==='g')return true;f++;}}return false;})(),
     'Italian: castling applied (king on g1)');

  // storage (guarded -- jsdom blocks file:// localStorage; real browsers allow it)
  try { ok(!!window.localStorage.getItem('openingTrainer.v1'), 'progress saved to localStorage'); }
  catch (e) { console.log('  - localStorage read blocked in jsdom (OK; works in real browsers)'); }

  console.log('\n' + (failed ? `FAILED (${failed})` : 'ALL UI CHECKS PASSED ✓'));
  process.exit(failed ? 1 : 0);
}
main().catch(e => { console.error(e); process.exit(2); });
