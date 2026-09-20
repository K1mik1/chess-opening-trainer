const assert=require('node:assert/strict');
const {chromium,webkit}=require('playwright');
const fixtures=[{"id": "normal", "startFen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "color": "white", "edges": [{"san": "e4", "uci": "e2e4", "from": "e2", "to": "e4", "mine": true, "castle": null, "ep": false, "node": {"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"}}], "myMoves": 1, "courseName": "Test", "name": "normal", "meta": {}}, {"id": "capture", "startFen": "4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1", "color": "white", "edges": [{"san": "exd5", "uci": "e4d5", "from": "e4", "to": "d5", "mine": true, "castle": null, "ep": false, "node": {"fen": "4k3/8/8/3P4/8/8/8/4K3 b - - 0 1"}}], "myMoves": 1, "courseName": "Test", "name": "capture", "meta": {}}, {"id": "castle-white", "startFen": "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "color": "white", "edges": [{"san": "O-O", "uci": "e1g1", "from": "e1", "to": "g1", "mine": true, "castle": {"from": "h1", "to": "f1"}, "ep": false, "node": {"fen": "r3k2r/8/8/8/8/8/8/R4RK1 b kq - 1 1"}}], "myMoves": 1, "courseName": "Test", "name": "castle-white", "meta": {}}, {"id": "castle-queen", "startFen": "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "color": "white", "edges": [{"san": "O-O-O", "uci": "e1c1", "from": "e1", "to": "c1", "mine": true, "castle": {"from": "a1", "to": "d1"}, "ep": false, "node": {"fen": "r3k2r/8/8/8/8/8/8/2KR3R b kq - 1 1"}}], "myMoves": 1, "courseName": "Test", "name": "castle-queen", "meta": {}}, {"id": "castle-black", "startFen": "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", "color": "black", "edges": [{"san": "O-O", "uci": "e8g8", "from": "e8", "to": "g8", "mine": true, "castle": {"from": "h8", "to": "f8"}, "ep": false, "node": {"fen": "r4rk1/8/8/8/8/8/8/R3K2R w KQ - 1 2"}}], "myMoves": 1, "courseName": "Test", "name": "castle-black", "meta": {}}, {"id": "en-passant", "startFen": "7k/8/8/3pP3/8/8/8/K7 w - d6 0 1", "color": "white", "edges": [{"san": "exd6", "uci": "e5d6", "from": "e5", "to": "d6", "mine": true, "castle": null, "ep": true, "node": {"fen": "7k/8/3P4/8/8/8/8/K7 b - - 0 1"}}], "myMoves": 1, "courseName": "Test", "name": "en-passant", "meta": {}}, {"id": "promotion", "startFen": "4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "color": "white", "edges": [{"san": "a8=Q+", "uci": "a7a8q", "from": "a7", "to": "a8", "mine": true, "castle": null, "ep": false, "node": {"fen": "Q3k3/8/8/8/8/8/8/4K3 b - - 0 1"}}], "myMoves": 1, "courseName": "Test", "name": "promotion", "meta": {}}, {"id": "black-promotion", "startFen": "4k3/8/8/8/8/8/p7/4K3 b - - 0 1", "color": "black", "edges": [{"san": "a1=Q+", "uci": "a2a1q", "from": "a2", "to": "a1", "mine": true, "castle": null, "ep": false, "node": {"fen": "4k3/8/8/8/8/8/8/q3K3 w - - 0 2"}}], "myMoves": 1, "courseName": "Test", "name": "black-promotion", "meta": {}}];
(async()=>{
 for(const [name,engine,options] of [['Chrome',chromium,{channel:'chrome'}],['WebKit',webkit,{}]]){
  const browser=await engine.launch({headless:true,...options});
  try{
   const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(process.env.PUZZLE_TEST_URL || 'http://localhost:8765/',{waitUntil:'domcontentloaded'});
   await page.evaluate(()=>Promise.all(pieceImages.map(img=>img.decode())));
   for(const fixture of fixtures){
    await page.evaluate(card=>beginSession([card],'animation-test',false),fixture);
    await page.waitForFunction(()=>play.awaiting);
    const result=await page.evaluate(async()=>{
      const edge=play.edges[0];
      const grid=[...board.children];
      const pieces=new Map([...board.querySelectorAll('.piece')].map(p=>[p.parentElement.dataset.square,p]));
      const moving=pieces.get(edge.from), image=moving.querySelector('img');
      // Sample fixed timeline positions: wall-clock frame counts are unreliable
      // when headless WebKit is throttled by the operating system.
      const probe=animatePiece(edge.from,edge.to);
      probe.animation.finished.catch(()=>{});
      probe.animation.pause();
      const positions=[0,120,240].map(t=>{
        probe.animation.currentTime=t;
        const r=moving.getBoundingClientRect(); return [r.x,r.y];
      });
      probe.animation.cancel(); boardAnimations.delete(probe.animation); moving.classList.remove('moving');
      const samples=[]; let finished=false;
      play.awaiting=false; engineBusy=true;
      const task=new Promise(resolve=>playEdge(edge,()=>{finished=true;resolve();}));
      while(!finished){
        await new Promise(requestAnimationFrame);
        samples.push({connected:moving.isConnected,imageSame:moving.querySelector('img')===image,
          imageReady:moving.querySelector('img').complete&&moving.querySelector('img').naturalWidth>0,x:moving.getBoundingClientRect().x,y:moving.getBoundingClientRect().y});
      }
      await task;
      const map=parseFEN(edge.node.fen);
      const unchanged=[...pieces].filter(([sq])=>sq!==edge.from&&sq!==edge.to&&sq!==edge.castle?.from&&pieces.get(sq).dataset.piece===map[sq]);
      return {stableGrid:grid.every((node,i)=>board.children[i]===node),
        stationaryStable:unchanged.every(([sq,p])=>sqEl(sq).querySelector('.piece')===p),
        movingSame:sqEl(edge.to).querySelector('.piece')===moving,
        positionCorrect:[...board.children].every(sq=>sq.querySelector('.piece')?.dataset.piece===map[sq.dataset.square]),
        samples, positions, animations:boardAnimations.size};
    });
    assert(result.stableGrid&&result.stationaryStable&&result.movingSame&&result.positionCorrect,`${name} ${fixture.id} node/position regression`);
    assert(result.samples.every(s=>s.connected&&(s.imageSame||fixture.id.includes('promotion'))&&s.imageReady),`${name} ${fixture.id} image gap`);
    assert.equal(new Set(result.positions.map(p=>p.join(','))).size,3,`${name} ${fixture.id} no interpolated positions`);
   }
   // Leaving mid-animation must not mutate a new training board.
   await page.evaluate(card=>beginSession([card],'animation-test',false),fixtures[0]);
   await page.waitForFunction(()=>play.awaiting);
   await page.evaluate(card=>{
     window.staleCallback=false;
     playEdge(play.edges[0],()=>{window.staleCallback=true;});
     go('home');beginSession([card],'animation-test',false);
   },fixtures[1]);
   await page.waitForTimeout(600);
   assert.equal(await page.evaluate(()=>window.staleCallback),false);
   assert.equal(await page.evaluate(()=>play.fen),fixtures[1].startFen);
   await page.emulateMedia({reducedMotion:'reduce'});
   await page.evaluate(()=>new Promise(resolve=>playEdge(play.edges[0],resolve)));
   assert.equal(await page.evaluate(()=>play.fen),fixtures[1].edges[0].node.fen);
   assert.deepEqual(errors,[]);
   console.log(`PASS ${name}: 8 move types, stable board and piece nodes, no missing image samples, intermediate frames, cancellation and reduced motion.`);
  }finally{await browser.close();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
