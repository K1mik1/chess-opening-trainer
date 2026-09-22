const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:390,height:844}}), errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8765/',{waitUntil:'domcontentloaded'});
 await page.locator('.books-entry').waitFor();
 assert.deepEqual(await page.locator('#homeMenus>section h2').allTextContents(),['Problemi di scacchi','Aperture','Libri']);
 assert.equal(await page.locator('.course-card').count(),0);
 for(const width of [375,390,1440]){
 await page.setViewportSize({width,height:900});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 }
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'/tmp/chess-home-v15.png',fullPage:true});
 await page.locator('[data-nav="openings"]').click();
 assert(await page.locator('.course-card').count()>0);
 await page.locator('.course-card').first().click();
 await page.locator('.course-detail [data-nav="openings"]').click();
 await page.evaluate(()=>beginSession([catalogueCards().find(c=>c.edges.length>=5)],'puzzle-practice',false));
 await page.waitForFunction(()=>play.awaiting);
 assert(await page.locator('#prevMove').isDisabled());
 const first=await page.evaluate(()=>play.edges[0]);
 await page.locator(`[data-square="${first.from}"]`).click();
 await page.locator(`[data-square="${first.to}"]`).click();
 await page.waitForFunction(()=>play.step>=2&&play.awaiting&&!engineBusy);
 const before=await page.evaluate(()=>({fen:play.fen,step:play.step,state:JSON.stringify(state)}));
 await page.locator('#prevMove').click();
 assert(await page.locator('#hintBtn').isDisabled());
 assert.equal(await page.evaluate(()=>play.reviewPly),before.step-1);
 await page.evaluate(()=>{onHint();onReveal();});
 assert.equal(await page.evaluate(()=>JSON.stringify(state)),before.state);
 await page.locator('#prevMove').click();
 assert(await page.locator('#prevMove').isDisabled());
 for(let i=0;i<before.step;i++) await page.locator('#nextMove').click();
 assert(await page.locator('#nextMove').isDisabled());
 assert(!(await page.locator('#hintBtn').isDisabled()));
 assert.deepEqual(await page.evaluate(()=>({fen:play.fen,step:play.step,state:JSON.stringify(state)})),before);
 for(let i=0;i<25 && !await page.locator('#nextPuzzle').count();i++){
 await page.waitForFunction(()=>play.awaiting&&!engineBusy||!!document.querySelector('#nextPuzzle'));
 if(await page.locator('#nextPuzzle').count()) break;
 const edge=await page.evaluate(()=>play.edges[play.step]);
 await page.locator(`[data-square="${edge.from}"]`).click();await page.locator(`[data-square="${edge.to}"]`).click();
 await page.waitForTimeout(350);
 }
 await page.locator('#nextPuzzle').waitFor();
 const solved=await page.evaluate(()=>JSON.stringify(state));
 await page.locator('#prevMove').click();await page.locator('#nextMove').click();
 assert.equal(await page.evaluate(()=>JSON.stringify(state)),solved);
 assert.equal(await page.locator('.train-info button:visible').first().getAttribute('id'),'nextPuzzle');
 for(const width of [375,390,1440]){
 await page.setViewportSize({width,height:900});
 const prev=await page.locator('#prevMove').boundingBox(), next=await page.locator('#nextMove').boundingBox();
 const finish=await page.locator('#finishPuzzles').boundingBox(), problem=await page.locator('#nextPuzzle').boundingBox();
 assert(prev.x<next.x && next.x<problem.x);
 assert(finish.y>prev.y && Math.abs(problem.y-prev.y)<1);
 assert(Math.abs(problem.y+problem.height-finish.y-finish.height)<1);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 }
 await page.setViewportSize({width:390,height:844});
 await page.locator('#puzzleCompletion').screenshot({path:'/tmp/chess-completion-v16.png'});
 await page.locator('#nextPuzzle').click();
 await page.waitForFunction(()=>play.step===0&&play.awaiting);
 assert.equal(await page.locator('.train-actions #puzzleHistory').count(),1);
 assert(await page.locator('#prevMove').isDisabled());
 assert.deepEqual(errors,[]);console.log('PASS: home ordering, mobile sizing, openings navigation, puzzle history without spoilers or grading changes.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
