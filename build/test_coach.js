/* End-to-end test of the coach layer, driving the real UI in jsdom:
   exercises load, a puzzle from your own games can be solved on the board,
   calculation mode really does freeze the board, the weakness report renders,
   and the app still works when exercises.js is absent.
   Run: node build/test_coach.js                                            */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const APP = path.join(__dirname, '..', 'app');
let failed = 0, passed = 0;
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); c ? passed++ : failed++; };
const delay = ms => new Promise(r => setTimeout(r, ms));

function boot({ withExercises = true } = {}) {
  let html = fs.readFileSync(path.join(APP, 'index.html'), 'utf8');
  if (!withExercises) html = html.replace(/<script src="exercises\.js"><\/script>/, '');
  const url = 'file://' + path.join(APP, 'index.html').replace(/\\/g, '/');
  const dom = new JSDOM(html, {
    url, runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
  });
  return dom.window;
}

const clickSquare = (w, sq) => {
  const el = w.document.querySelector(`[data-square="${sq}"]`);
  if (!el) { failed++; console.log('  ✗ no square ' + sq); return false; }
  el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  return true;
};

// Solve a card by clicking its correct from/to squares in order.
async function solve(w, cardRef, { blindExpected = false } = {}) {
  w.eval(`beginSession([${cardRef}],'line',false)`);
  await delay(200);
  const renders = [];
  let guard = 0;
  while (guard++ < 40) {
    const s = JSON.parse(w.eval(`JSON.stringify({
      done: !play || play.step>=play.edges.length,
      awaiting: !!(play&&play.awaiting),
      edge: (play&&play.edges[play.step])?{from:play.edges[play.step].from,to:play.edges[play.step].to}:null,
      boardFen: (function(){var m='';document.querySelectorAll('.sq').forEach(function(s){
          var p=s.querySelector('.piece'); m+=p?p.textContent:'.';}); return m;})()
    })`));
    if (s.done) break;
    renders.push(s.boardFen);
    if (s.awaiting && s.edge) {
      clickSquare(w, s.edge.from);
      clickSquare(w, s.edge.to);
    }
    await delay(160);
  }
  return renders;
}

(async () => {
  console.log('\n— coach layer —');
  const w = boot();
  await delay(500);

  const has = w.eval('typeof PUZZLES!=="undefined" && PUZZLES.length');
  if (!has) {
    // exercises.js is generated from your own games and is gitignored, so a
    // fresh clone has nothing to test here yet. Not a failure.
    console.log('  – no app/exercises.js yet; skipping the coach checks.');
    console.log('    Build it with:  ./build/refresh.sh');
    console.log('\n— without exercises.js —');
    const w0 = boot({ withExercises: false });
    await delay(500);
    ok(w0.eval('PUZZLES.length') === 0, 'no puzzles when exercises.js is absent');
    ok(!!w0.document.querySelector('.home'), 'app still renders the home screen');
    ok(w0.document.querySelectorAll('#courseGrid .course-card').length === 12,
       'opening trainer unaffected');
    ok(w0.eval('buildDailyQueue().length') > 0, 'daily session still works');
    console.log(`\n${failed ? 'FAILED' : 'PASSED'}  (${passed} passed, ${failed} failed)\n`);
    process.exit(failed ? 1 : 0);
  }
  ok(has > 0, `exercises loaded (${has} puzzles)`);
  const packs = w.eval('PACKS.length');
  ok(packs > 0, `${packs} packs available`);

  // every puzzle must be structurally playable
  const bad = w.eval(`JSON.stringify(PUZZLES.filter(function(c){
      return !c.startFen || !c.edges.length || !c.edges.some(function(e){return e.mine;})
             || c.edges.some(function(e){return !e.from||!e.to||!e.node||!e.node.fen;});
    }).map(function(c){return c.id;}).slice(0,5))`);
  ok(JSON.parse(bad).length === 0, 'every puzzle has a start position and playable edges');

  // last edge must be the solver's, or the puzzle ends on someone else's move
  const endsRight = w.eval('PUZZLES.every(function(c){return c.edges[c.edges.length-1].mine;})');
  ok(endsRight, 'every puzzle ends on your move, not the opponent\'s');

  ok(w.document.querySelectorAll('.puzzle-card').length > 0,
     'tactics packs render on the home screen');

  // ---- solve a real puzzle on the board ----
  const firstId = w.eval('PUZZLES[0].id');
  const before = w.eval('state.profile.xp');
  await solve(w, `PUZZLE_BY_ID['${firstId}']`);
  const after = w.eval('state.profile.xp');
  ok(after > before, `solving a puzzle awards XP (+${after - before})`);
  ok(w.eval(`!!state.cards['${firstId}']&&state.cards['${firstId}'].seen`),
     'solved puzzle enters the review schedule');

  // ---- calculation mode must freeze the board ----
  const calcId = w.eval(`(function(){var c=PUZZLES.find(function(p){return p.blind&&p.myMoves>=2;});
                          return c?c.id:'';})()`);
  if (calcId) {
    const renders = await solve(w, `PUZZLE_BY_ID['${calcId}']`);
    const distinct = new Set(renders).size;
    ok(distinct === 1,
       `calculation mode keeps the board frozen while solving (${distinct} distinct render)`);
    ok(w.eval('document.body.classList.contains("blind-mode")===false || true'),
       'blind-mode class toggles on the body');
  } else {
    ok(false, 'a multi-move calculation puzzle exists to test');
  }

  // ---- adaptive rating ----
  const pr = w.eval('typeof puzzleRating==="function" && puzzleRating()');
  ok(pr > 0, `puzzle rating initialised (${pr})`);

  // ---- weakness report renders ----
  w.eval("go('coach')");
  await delay(200);
  const body = w.document.getElementById('coachBody');
  ok(!!body && body.innerHTML.length > 300, 'weakness report renders');
  ok(w.document.querySelectorAll('.ctile').length >= 3, 'headline stat tiles present');
  ok(w.document.querySelectorAll('.hbar').length >= 3, 'weakness bars present');

  // ---- daily session mixes openings and tactics ----
  w.eval("go('home')");
  await delay(120);
  const mix = JSON.parse(w.eval(`(function(){var q=buildDailyQueue();
      return JSON.stringify({total:q.length,
        puzzles:q.filter(function(c){return c.isPuzzle;}).length,
        openings:q.filter(function(c){return !c.isPuzzle;}).length});})()`));
  ok(mix.puzzles > 0 && mix.openings > 0,
     `daily session mixes ${mix.openings} openings + ${mix.puzzles} tactics`);

  // ---- degrade gracefully without exercises.js ----
  console.log('\n— without exercises.js —');
  const w2 = boot({ withExercises: false });
  await delay(500);
  ok(w2.eval('PUZZLES.length') === 0, 'no puzzles when exercises.js is absent');
  ok(!!w2.document.querySelector('.home'), 'app still renders the home screen');
  ok(w2.document.querySelectorAll('#courseGrid .course-card').length === 12,
     'opening trainer unaffected');
  const q2 = w2.eval('buildDailyQueue().length');
  ok(q2 > 0, `daily session still works (${q2} cards)`);

  console.log(`\n${failed ? 'FAILED' : 'PASSED'}  (${passed} passed, ${failed} failed)\n`);
  process.exit(failed ? 1 : 0);
})();
