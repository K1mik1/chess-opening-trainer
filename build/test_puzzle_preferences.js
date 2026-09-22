const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
 const context=await browser.newContext({viewport:{width:390,height:844}});
 let page=await context.newPage();const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8765/',{waitUntil:'domcontentloaded'});
 await page.locator('[data-nav="puzzles"]').click();
 await page.locator('#puzzleLevel').selectOption('sfida');
 await page.locator('#puzzleTheme').selectOption('lichess-mateIn1');
 await page.close();page=await context.newPage();
 await page.goto('http://localhost:8765/',{waitUntil:'domcontentloaded'});
 assert.match(await page.locator('#savedPuzzleSelection').innerText(),/Sfida/);
 await page.locator('#startSavedPuzzles').click();
 await page.waitForFunction(()=>play.awaiting);
 assert(await page.evaluate(()=>session.queue.every(c=>catalogueLevel(c.meta.rating)==='sfida'&&c.packId==='lichess-mateIn1')&&session.puzzlePool.every(c=>catalogueLevel(c.meta.rating)==='sfida'&&c.packId==='lichess-mateIn1')));
 await page.evaluate(()=>go('puzzles'));
 assert.equal(await page.locator('#puzzleLevel').inputValue(),'sfida');
 assert.equal(await page.locator('#puzzleTheme').inputValue(),'lichess-mateIn1');
 await page.evaluate(()=>{for(const c of selectedPuzzleCards()){schedule(c.id,'easy');recordCatalogueCompletion(c);}save();go('home');});
 await page.locator('#startSavedPuzzles').click();
 assert.equal(await page.locator('#board').count(),0);
 assert.equal(await page.evaluate(()=>puzzlePreferences().level),'sfida');
 await page.evaluate(()=>go('puzzles'));
 await page.locator('#puzzleTheme').selectOption('all');
 await page.locator('#puzzleLevel').selectOption('base');
 await page.evaluate(()=>go('home'));
 await page.screenshot({path:'/tmp/chess-preferences-v17.png',fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 console.log('PASS: saved difficulty/theme survive reopening, direct start and continuation pool respect selection, exhaustion never changes level.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
