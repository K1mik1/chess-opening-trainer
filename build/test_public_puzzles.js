// Run with Playwright installed and the app served locally; PUZZLE_TEST_URL can
// point at production to verify that the published catalogue is complete.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try {
    const context=await browser.newContext({viewport:{width:390,height:844}});
    const page=await context.newPage();
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    await page.goto(process.env.PUZZLE_TEST_URL || 'http://localhost:8765/',{waitUntil:'domcontentloaded'});
    const catalogue=await page.evaluate(()=>catalogueCards().map(c=>({id:c.id,pack:c.packId,rating:c.meta.rating,endsMine:c.edges.at(-1).mine})));
    assert.equal(catalogue.length,200); assert.equal(new Set(catalogue.map(c=>c.id)).size,200);
    assert(catalogue.every(c=>c.endsMine));
    const bands=await page.evaluate(()=>['base','medio','sfida'].map(b=>catalogueCards().filter(c=>catalogueLevel(c.meta.rating)===b).length));
    assert.deepEqual(bands,[80,80,40]);
    await page.locator('[data-nav="puzzles"]').click();
    assert.equal(await page.locator('.puzzle-row').count(),200);
    await page.locator('#puzzleTheme').selectOption('lichess-mateIn1');
    assert.equal(await page.locator('.puzzle-row').count(),25);
    await page.locator('#puzzleLevel').selectOption('base');
    assert.equal(await page.locator('.puzzle-row').count(),10);
    await page.locator('#puzzleMixed').click();
    await page.waitForFunction(()=>play.awaiting);
    assert(!/Matto|mate/i.test(await page.locator('#lineName').innerText()));
    assert(await page.locator('#planCard').isHidden());
    assert.equal(await page.locator('#board').evaluate(e=>e.getBoundingClientRect().width),382);
    await page.locator('#hintBtn').click();
    const firstId=await page.evaluate(()=>play.card.id);
    const solve = async () => {
      for(let n=0;n<30;n++){
        if(await page.locator('#nextPuzzle').count()) return;
        await page.waitForFunction(()=>play.awaiting || !!document.querySelector('#nextPuzzle'));
        if(await page.locator('#nextPuzzle').count()) return;
        const edge=await page.evaluate(()=>play.edges[play.step]);
        await page.locator(`[data-square="${edge.from}"]`).click();
        await page.locator(`[data-square="${edge.to}"]`).click();
        await page.waitForTimeout(400);
      }
      throw Error('Puzzle did not finish');
    };
    await solve();
    assert(await page.evaluate(id=>srs(id).needsReview,firstId));
    assert(await page.locator('#planCard').isVisible());
    await page.locator('[data-nav="home"]').first().click();
    await page.locator('[data-nav="puzzles"]').click();
    assert.match(await page.locator('#puzzleReview').innerText(),/\(1\)/);
    await page.locator('#puzzleReview').click();
    await solve();
    assert.equal(await page.evaluate(id=>srs(id).needsReview,firstId),false);
    await page.locator('#nextPuzzle').click();
    await page.locator('#sumTitle').waitFor();
    await page.evaluate(()=>go('puzzles'));
    await page.locator('#puzzleTheme').selectOption('lichess-mateIn2');
    await page.locator('.puzzle-row').first().click();
    await solve();
    assert.equal(await page.evaluate(()=>play.wrong),0);
    assert.equal(await page.evaluate(()=>play.step),3);
    await page.evaluate(()=>navigator.serviceWorker.ready);
    await context.setOffline(true);
    await page.reload({waitUntil:'domcontentloaded'});
    await page.locator('[data-nav="puzzles"]').click();
    assert.equal(await page.locator('.puzzle-row').count(),200);
    assert.equal(await page.evaluate(id=>srs(id).needsReview,firstId),false);
    await context.setOffline(false);
    // Shared training code must still finish an opening after the puzzle changes.
    await page.evaluate(()=>beginSession([CARDS.slice().sort((a,b)=>a.edges.length-b.edges.length)[0]],'learn',true));
    await page.locator('#sumTitle').waitFor({timeout:30000});
    assert.match(await page.locator('#sumTitle').innerText(),/Lesson complete/);
    assert.deepEqual(errors,[]);
    console.log('PASS: 200 unique puzzles; category/level filters; hidden mixed themes; hint review; clean retry; multi-move solution; offline catalogue and saved progress; opening lesson regression.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
