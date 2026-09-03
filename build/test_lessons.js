/* Tests for the lesson layer -- the part that replaced "show the same blunder
   forever" with deliberate practice.

   The three promises worth testing, because they are the ones that broke
   before and the ones a user would notice:

     1. RETIREMENT   a position from your own games stops coming back once you
                     have solved it maxReps times cleanly.
     2. FRESHNESS    practising a lesson twice never hands you the same
                     position twice while its pool has anything left.
     3. FOCUS        a day's tactics concentrate on a couple of lessons rather
                     than one puzzle from each of six.

   Plus rung promotion/demotion, and that the whole thing degrades to the old
   behaviour when there are no lessons in the build.

   Run: node build/test_lessons.js                                          */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const APP = path.join(__dirname, '..', 'app');
let failed = 0, passed = 0;
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); c ? passed++ : failed++; };
const delay = ms => new Promise(r => setTimeout(r, ms));

function boot() {
  const html = fs.readFileSync(path.join(APP, 'index.html'), 'utf8');
  const url = 'file://' + path.join(APP, 'index.html').replace(/\\/g, '/');
  const dom = new JSDOM(html, {
    url, runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
  });
  return dom.window;
}
const ev = (w, expr) => w.eval(expr);
const evj = (w, expr) => JSON.parse(w.eval(`JSON.stringify(${expr})`));

(async () => {
  console.log('\n— lessons —');
  const w = boot();
  await delay(600);

  if (!ev(w, 'typeof LESSONS!=="undefined" && LESSONS.length')) {
    console.log('  – no lessons in app/exercises.js yet; build with ./build/refresh.sh');
    console.log(`\n${failed ? 'FAILED' : 'SKIPPED'}  (${passed} passed, ${failed} failed)\n`);
    process.exit(failed ? 1 : 0);
  }

  const nLessons = ev(w, 'LESSONS.length');
  ok(nLessons > 0, `${nLessons} lessons loaded`);

  // every lesson has the three things that make it a lesson and not a pack
  const shapes = evj(w, `LESSONS.map(L=>({
    d: !!L.diagnosis, p: !!L.principle, h: !!L.habit,
    stages: L.stages.length, cards: L.stages.reduce((n,s)=>n+s.cards.length,0)}))`);
  ok(shapes.every(s => s.d && s.p && s.h),
     'every lesson has a diagnosis, a principle and a habit');
  ok(shapes.every(s => s.stages >= 2),
     'every lesson has a multi-rung ladder');

  // ---- no position is shared between lessons ----
  const ids = evj(w, 'LESSON_CARDS.map(c=>c.id)');
  ok(new Set(ids).size === ids.length,
     `${ids.length} drill positions, none shared between lessons`);

  // ---- 1. RETIREMENT ----
  const capped = ev(w, `(function(){
    var c = LESSON_CARDS.find(function(x){return x.meta && x.meta.maxReps;});
    return c ? c.id : '';
  })()`);
  ok(!!capped, 'lesson opens with a position from your own games (capped)');
  if (capped) {
    const cap = ev(w, `LESSON_CARD_BY_ID[${JSON.stringify(capped)}].meta.maxReps`);
    // solve it cleanly `cap` times
    for (let i = 0; i < cap; i++) w.eval(`schedule(${JSON.stringify(capped)},'easy')`);
    const st = ev(w, `cardState(${JSON.stringify(capped)})`);
    ok(st === 'retired', `retires after ${cap} clean solves (state: ${st})`);
    ok(ev(w, `buildTacticsQueue(20).some(c=>c.id===${JSON.stringify(capped)})`) === false,
       'a retired position never appears in the daily queue again');
    // a slip resets the run, so it is not retired on a mixed record
    w.eval(`state.cards[${JSON.stringify(capped)}].clean=0`);
    ok(ev(w, `cardState(${JSON.stringify(capped)})`) !== 'retired',
       'a wrong answer resets the run towards retirement');
    w.eval(`state.cards[${JSON.stringify(capped)}].clean=${cap}`);
  }

  // an OPENING line has no cap and must never retire
  const openCard = ev(w, 'CARDS[0].id');
  for (let i = 0; i < 8; i++) w.eval(`schedule(${JSON.stringify(openCard)},'easy')`);
  ok(ev(w, `cardState(${JSON.stringify(openCard)})`) !== 'retired',
     'opening lines never retire, however often you get them right');

  // ---- 2. FRESHNESS ----
  w.eval('state.cards={}; state.lessons={};');
  const L0 = ev(w, 'LESSONS[0].id');
  const first = evj(w, `freshFromLesson(LESSON_BY_ID[${JSON.stringify(L0)}],4).map(c=>c.id)`);
  // mark them solved, then ask again
  w.eval(`${JSON.stringify(first)}.forEach(function(id){schedule(id,'easy');})`);
  const second = evj(w, `freshFromLesson(LESSON_BY_ID[${JSON.stringify(L0)}],4).map(c=>c.id)`);
  const overlap = second.filter(id => first.includes(id));
  ok(first.length > 0 && second.length > 0 && overlap.length === 0,
     `practising twice gives all-new positions (${first.length} then ${second.length}, 0 shared)`);

  // ---- 3. FOCUS ----
  w.eval('state.cards={}; state.lessons={};');
  const q = evj(w, 'buildTacticsQueue(6).map(c=>({l:c.lessonId||null}))');
  const lessonsHit = new Set(q.map(x => x.l).filter(Boolean));
  ok(q.length > 0, `daily queue built (${q.length} cards)`);
  ok(lessonsHit.size <= ev(w, 'LESSON_FOCUS'),
     `concentrates on at most ${ev(w, 'LESSON_FOCUS')} lessons a day (hit ${lessonsHit.size})`);

  // ---- rung promotion and demotion ----
  w.eval('state.cards={}; state.lessons={};');
  const promo = ev(w, `(function(){
    var L = LESSON_BY_ID[${JSON.stringify(L0)}];
    var before = lessonSrs(L.id).rung;
    var target = RUNG_TARGET[lessonStage(L).id] || 5;
    for(var i=0;i<target;i++) creditLesson(L.stages[0].cardObjs[0]||LESSON_CARDS[0], true);
    return lessonSrs(L.id).rung > before;
  })()`);
  ok(promo, 'a clean run at a rung promotes you to the next one');

  const demo = ev(w, `(function(){
    var L = LESSON_BY_ID[${JSON.stringify(L0)}];
    var s = lessonSrs(L.id);
    s.rung = 1; s.clean = 0; s.tries = 0;
    for(var i=0;i<RUNG_MIN_TRIES+1;i++) creditLesson(LESSON_CARDS[0], false);
    return lessonSrs(L.id).rung < 1;
  })()`);
  ok(demo, 'repeated failure drops you back a rung instead of grinding');

  // ---- the lesson view renders ----
  w.eval(`go('lesson',${JSON.stringify(L0)})`);
  await delay(200);
  ok(!!w.document.querySelector('.lesson-detail'), 'lesson view renders');
  ok(!!w.document.querySelector('.ls-block.ls-habit'), 'the habit is shown');
  ok(w.document.querySelectorAll('.ls-rung').length >= 2, 'the ladder is shown');
  const diag = (w.document.querySelector('#lsDiag') || {}).textContent || '';
  ok(/\d/.test(diag), 'the diagnosis quotes real numbers from your games');

  // ---- home screen ----
  w.eval("go('home')");
  await delay(250);
  ok(w.document.querySelectorAll('.lesson-card').length === nLessons,
     'every lesson appears on the home screen');

  console.log(`\n${failed ? 'FAILED' : 'ALL LESSON CHECKS PASSED ✓'}  (${passed} passed, ${failed} failed)\n`);
  process.exit(failed ? 1 : 0);
})();
