/* Validate the generated move-tree (app/repertoire.js) for structural integrity.
   Run: node build/test_tree.js
   Checks, for every node/edge:
     - turn alternates correctly and matches edge.mine vs course colour
     - the moving piece actually exists on its 'from' square in the parent FEN
     - the 'to' square holds that piece in the child FEN (move really applied)
     - castling edges carry rook hops; child FEN shows the rook moved
     - leaf counts match the generator's reported stats
*/
const fs = require('fs');
const path = require('path');

global.window = {};
require(path.join(__dirname, '..', 'app', 'repertoire.js'));
const COURSES = global.window.REPERTOIRE;

function parseFEN(fen){
  const rows = fen.split(' ')[0].split('/'); const map = {};
  for (let r=0;r<8;r++){ let f=0;
    for (const ch of rows[r]){ if(/\d/.test(ch)) f+=+ch; else { map['abcdefgh'[f]+(8-r)]=ch; f++; } }
  } return map;
}
const turnOf = fen => fen.split(' ')[1];   // 'w' | 'b'

let errors = 0, nodes = 0, edges = 0, leaves = 0;
function fail(msg){ errors++; console.log('  ✗ '+msg); }

for (const course of COURSES){
  const myColor = course.color === 'white' ? 'w' : 'b';
  let cLeaves = 0, cMy = 0;

  (function walk(node){
    nodes++;
    if (!node.children.length){ cLeaves++; return; }
    for (const e of node.children){
      edges++;
      const pmap = parseFEN(node.fen);
      const cmap = parseFEN(e.node.fen);

      // turn: the side to move in the PARENT must be the side making this move
      const mover = turnOf(node.fen);
      const expectedMine = (mover === myColor);
      if (e.mine !== expectedMine)
        fail(`${course.id}: edge ${e.san} mine=${e.mine} but mover=${mover}/${myColor}`);

      // child turn must be the opposite
      if (turnOf(e.node.fen) === mover)
        fail(`${course.id}: ${e.san} did not flip side to move`);

      // piece must exist on 'from' in parent and be the mover's colour
      const pc = pmap[e.from];
      if (!pc) fail(`${course.id}: ${e.san} no piece on ${e.from} (parent)`);
      else { const isWhite = pc === pc.toUpperCase();
        if (isWhite !== (mover==='w'))
          fail(`${course.id}: ${e.san} piece on ${e.from} wrong colour`); }

      // 'to' square in child must hold a piece (the one that moved / promoted)
      if (!cmap[e.to]) fail(`${course.id}: ${e.san} nothing on ${e.to} (child)`);

      // 'from' square in child must be empty (piece left), unless en passant edge cases
      if (cmap[e.from] && !e.castle)
        fail(`${course.id}: ${e.san} piece still on ${e.from} after move`);

      // castling: rook hop present and applied
      if (e.castle){
        if (!cmap[e.castle.to]) fail(`${course.id}: ${e.san} rook missing on ${e.castle.to}`);
        if (cmap[e.castle.from]) fail(`${course.id}: ${e.san} rook still on ${e.castle.from}`);
      }
      if (e.mine) cMy++;
      walk(e.node);
    }
  })(course.tree);

  leaves += cLeaves;
  const ok = cLeaves === course.stats.variations && cMy === course.stats.quizMoves;
  console.log(`${ok?'✓':'✗'} ${course.name}: ${cLeaves} leaves (stats ${course.stats.variations}), `
            + `${cMy} my-moves (stats ${course.stats.quizMoves})`);
  if (!ok) errors++;
}

console.log(`\n${nodes} nodes, ${edges} edges, ${leaves} variations checked.`);
console.log(errors ? `FAILED with ${errors} error(s).` : 'ALL CHECKS PASSED ✓');
process.exit(errors ? 1 : 0);
