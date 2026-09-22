// Playwright integration test; PUZZLE_TEST_URL can target the published app.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844},timezoneId:'Europe/Rome'});
  const page=await context.newPage(), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.clock.setFixedTime(new Date('2026-09-21T12:00:00+02:00'));
  await page.goto(process.env.PUZZLE_TEST_URL||'http://localhost:8765/?test=puzzles9',{waitUntil:'domcontentloaded'});
  const catalogue=await page.evaluate(()=>catalogueCards().map(c=>({id:c.id,fen:c.startFen.split(' ').slice(0,4).join(' '),endsMine:c.edges.at(-1).mine})));
  const CATALOGUE_SIZE=catalogue.length;
  assert(CATALOGUE_SIZE>=2000,`catalogo troppo piccolo: ${CATALOGUE_SIZE}`);
  assert.equal(new Set(catalogue.map(c=>c.id)).size,CATALOGUE_SIZE);
  assert.equal(new Set(catalogue.map(c=>c.fen)).size,CATALOGUE_SIZE);assert(catalogue.every(c=>c.endsMine));
  // Le quote per fascia cambiano quando si rigenera il catalogo: qui conta
  // che i tre livelli esistano, siano non vuoti e coprano tutto il catalogo.
  const perLevel=await page.evaluate(()=>['base','medio','sfida'].map(b=>catalogueCards().filter(c=>catalogueLevel(c.meta.rating)===b).length));
  assert(perLevel.every(n=>n>0),`livello vuoto: ${perLevel}`);
  assert.equal(perLevel.reduce((a,b)=>a+b,0),CATALOGUE_SIZE);
  await page.locator('[data-nav="puzzles"]').click();
  assert.equal(await page.locator('.puzzle-row').count(),100);
  assert.match(await page.locator('#puzzleCount').innerText(),new RegExp(`${CATALOGUE_SIZE} problemi`));
  await page.locator('#puzzleMore').click();assert.equal(await page.locator('.puzzle-row').count(),200);
  await page.locator('#puzzleTheme').selectOption('lichess-mateIn1');
  // Quanti ne conti dipende dalle quote del catalogo: si chiede all'app.
  const perTheme=await page.evaluate(()=>catalogueCards().filter(c=>c.packId==='lichess-mateIn1').length);
  assert.match(await page.locator('#puzzleCount').innerText(),new RegExp(`${perTheme} problemi`));
  await page.locator('#puzzleLevel').selectOption('base');
  const baseRows=await page.evaluate(()=>catalogueCards().filter(c=>c.packId==='lichess-mateIn1'&&catalogueLevel(c.meta.rating)==='base').length);
  assert.equal(await page.locator('.puzzle-row').count(),Math.min(100,baseRows));
  assert(await page.locator('#puzzleMore').isHidden());
  await page.locator('#puzzleMixed').click();await page.waitForFunction(()=>play.awaiting);
  assert(!/Matto|mate/i.test(await page.locator('#lineName').innerText()));assert(await page.locator('#planCard').isHidden());
  const firstId=await page.evaluate(()=>play.card.id);
  await page.locator('#hintBtn').click();
  const solve=async()=>{
   for(let n=0;n<30;n++){
    if(await page.locator('#nextPuzzle').count())return;
    await page.waitForFunction(()=>play.awaiting||!!document.querySelector('#nextPuzzle'));
    if(await page.locator('#nextPuzzle').count())return;
    const edge=await page.evaluate(()=>play.edges[play.step]);
    await page.locator(`[data-square="${edge.from}"]`).click();await page.locator(`[data-square="${edge.to}"]`).click();
    await page.waitForTimeout(350);
   }
   throw Error('Puzzle did not finish');
  };
  await solve();
  assert.equal(await page.evaluate(()=>state.profile.catalogueCompletions),1);
  assert(await page.evaluate(id=>srs(id).needsReview,firstId));
  assert.equal(await page.locator('.train-info button:visible').first().getAttribute('id'),'nextPuzzle');
  await page.locator('#nextPuzzle').click();await page.waitForFunction(id=>play.card.id!==id&&play.awaiting,firstId);
  await page.evaluate(()=>go('puzzles'));
  assert(await page.locator('#puzzleReview').isDisabled());
  assert(!(await page.evaluate(({id,size})=>buildTacticsQueue(size).some(c=>c.id===id),{id:firstId,size:CATALOGUE_SIZE})));
  // Expiry requires BOTH a later local date and 50 other completions.
  const otherIds=await page.evaluate(id=>catalogueCards().filter(c=>c.id!==id).slice(0,50).map(c=>c.id),firstId);
  const complete=ids=>page.evaluate(ids=>{for(const id of ids){schedule(id,'easy');recordCatalogueCompletion(PUZZLE_BY_ID[id]);}save();},ids);
  await complete(otherIds.slice(0,49));
  await page.clock.setFixedTime(new Date('2026-09-22T12:00:00+02:00'));
  assert.equal(await page.evaluate(id=>catalogueAvailable(PUZZLE_BY_ID[id]),firstId),false);
  await complete(otherIds.slice(49));
  assert.equal(await page.evaluate(id=>catalogueAvailable(PUZZLE_BY_ID[id]),firstId),true);
  await page.clock.setFixedTime(new Date('2026-09-21T18:00:00+02:00'));
  assert.equal(await page.evaluate(id=>catalogueAvailable(PUZZLE_BY_ID[id]),firstId),false);
  await page.clock.setFixedTime(new Date('2026-09-22T12:00:00+02:00'));
  await page.evaluate(()=>go('puzzles'));await page.locator('#puzzleReview').click();await solve();
  assert.equal(await page.evaluate(id=>srs(id).needsReview,firstId),false);
  assert.equal(await page.locator('#nextPuzzle').innerText(),'Scegli altri problemi');
  await page.locator('#nextPuzzle').click();await page.locator('#puzzleCount').waitFor();
  // Direct starts and daily review cannot bypass the cooldown, even after a lapse.
  await page.evaluate(id=>{srs(id).due=today();srs(id).lastGrade='again';beginSession([PUZZLE_BY_ID[id]],'line',false);},firstId);
  assert.equal(await page.locator('#board').count(),0);
  assert(!(await page.evaluate(({id,size})=>buildTacticsQueue(size).some(c=>c.id===id),{id:firstId,size:CATALOGUE_SIZE})));
  await page.locator('#puzzleTheme').selectOption('lichess-mateIn2');
  const expected=await page.locator('.puzzle-row:enabled .cl-top b').nth(1).innerText();
  await page.locator('.puzzle-row:enabled').first().click();await solve();
  assert.equal(await page.evaluate(()=>play.step),3);
  await page.locator('#nextPuzzle').click();await page.waitForFunction(name=>play.card.name===name,expected);
  await solve();await page.locator('#finishPuzzles').click();await page.locator('#sumTitle').waitFor();
  await page.evaluate(()=>navigator.serviceWorker.ready);await context.setOffline(true);
  await page.reload({waitUntil:'domcontentloaded'});await page.locator('[data-nav="puzzles"]').click();
  assert.equal(await page.evaluate(()=>catalogueCards().length),CATALOGUE_SIZE);
  assert.equal(await page.evaluate(id=>catalogueAvailable(PUZZLE_BY_ID[id]),firstId),false);
  assert.equal(await page.evaluate(()=>state.profile.catalogueCompletions),54);
  await context.setOffline(false);
  await page.evaluate(()=>beginSession([CARDS.slice().sort((a,b)=>a.edges.length-b.edges.length)[0]],'learn',true));
  await page.locator('#sumTitle').waitFor({timeout:30000});assert.match(await page.locator('#sumTitle').innerText(),/Lesson complete/);
  assert.deepEqual(errors,[]);
  console.log(`PASS: ${CATALOGUE_SIZE} unique positions, paging, filters, mixed sessions, daily+50 cooldown at 49/50 boundary, review/direct/daily guards, sequential puzzles, offline persistence and openings.`);
  // Old progress is preserved; timestamps absent in old backups migrate once.
  const legacy=await browser.newContext({viewport:{width:390,height:844},timezoneId:'Europe/Rome'});
  await legacy.addInitScript(id=>{if(!localStorage.getItem('openingTrainer.v1'))localStorage.setItem('openingTrainer.v1',JSON.stringify({v:1,profile:{xp:123},cards:{[id]:{seen:true,ease:2.7,interval:7,due:20700,reps:3,lapses:1,needsReview:true}}}));},firstId);
  const oldPage=await legacy.newPage();await oldPage.clock.setFixedTime(new Date('2026-09-21T12:00:00+02:00'));
  await oldPage.goto(process.env.PUZZLE_TEST_URL||'http://localhost:8765/',{waitUntil:'domcontentloaded'});
  assert.equal(await oldPage.evaluate(()=>state.profile.xp),123);
  assert.equal(await oldPage.evaluate(id=>srs(id).ease,firstId),2.7);
  assert.equal(await oldPage.evaluate(id=>srs(id).lastPuzzleDay,firstId),'2026-09-21');
  await oldPage.clock.setFixedTime(new Date('2026-09-22T12:00:00+02:00'));
  await oldPage.reload({waitUntil:'domcontentloaded'});
  assert.equal(await oldPage.evaluate(id=>srs(id).lastPuzzleDay,firstId),'2026-09-21');
  assert.equal(await oldPage.evaluate(id=>catalogueAvailable(PUZZLE_BY_ID[id]),firstId),false);
  console.log('PASS: legacy progress retained and cooldown migration persisted without restarting each day.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
