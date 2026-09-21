/* Smoke test del lettore dei corsi da libro (app/books.js).

   Gira su WebKit perche' il bersaglio e' l'iPhone: e' li' che l'app viene
   usata, e IndexedDB e i file picker si comportano diversamente dal desktop.
   Il corso NON e' nel repo (e' materiale del libro), quindi il file arriva da
   BOOK_COURSE_FILE. */
const assert = require('node:assert/strict');
const {webkit} = require('playwright');

const COURSE = process.env.BOOK_COURSE_FILE;
const URL_ = process.env.BOOK_TEST_URL || 'http://localhost:8765/';

(async () => {
  if(!COURSE){ console.error('BOOK_COURSE_FILE non impostata'); process.exit(2); }
  const browser = await webkit.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    await page.goto(URL_, {waitUntil: 'domcontentloaded'});
    await page.click('[data-nav="books"]');
    await page.waitForSelector('#bookImport');

    const chooser = page.waitForEvent('filechooser');
    await page.click('#bookImport');
    await (await chooser).setFiles(COURSE);
    await page.waitForSelector('.book-course .cd-line');

    const games = await page.$$eval('.book-course .cd-line', els => els.length);
    assert.ok(games >= 1, 'nessuna partita importata');

    await page.click('.book-course .cd-line');
    await page.waitForSelector('#bookNext');

    // Posizione iniziale: 32 pezzi, e il commento e' vuoto finche' non si muove
    assert.equal(await page.$$eval('#board .piece', p => p.length), 32, 'posizione iniziale errata');

    for(let i = 0; i < 6; i++){
      await page.click('#bookNext');
      await page.waitForTimeout(320);          // lascia finire l'animazione
    }
    const after = await page.evaluate(() => ({
      counter: document.querySelector('#bookCount').textContent,
      move: document.querySelector('#bookMove').textContent.trim(),
      comment: document.querySelector('#bookComment').textContent.trim().length,
      pieces: document.querySelectorAll('#board .piece').length,
      highlighted: document.querySelectorAll('#board .lastfrom, #board .lastto').length,
    }));
    assert.equal(after.counter, '6 / 55', `contatore inatteso: ${after.counter}`);
    // sei semimosse: 1.e4 e5 2.Nf3 Nc6 3.Bb5 a6
    assert.match(after.move, /^3…\s*a6$/, `mossa inattesa: ${after.move}`);
    assert.ok(after.comment > 40, 'commento mancante');
    assert.equal(after.highlighted, 2, 'ultima mossa non evidenziata');
    assert.equal(after.pieces, 32, 'pezzi persi dalla scacchiera');

    // Il segnalibro deve sopravvivere al ritorno alla lista e al rientro
    await page.click('[data-nav="books"]');
    await page.waitForSelector('.book-course .cd-line');
    await page.click('.book-course .cd-line');
    await page.waitForSelector('#bookCount');
    assert.equal(await page.textContent('#bookCount'), '6 / 55', 'segnalibro non ripreso');

    // Le immagini dei pezzi vanno decodificate prima dello scatto, altrimenti
    // lo screenshot mostra una scacchiera vuota che sembra un bug e non lo e'.
    await page.evaluate(() => Promise.all(
      [...document.querySelectorAll('#board .piece img')].map(i => i.decode().catch(() => {}))));
    await page.screenshot({path: process.env.BOOK_SHOT || 'book-reader.png'});
    assert.deepEqual(errors, [], 'errori JS in pagina');
    console.log('OK · import, navigazione, commento, evidenziazione, segnalibro');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error('FALLITO:', e.message); process.exit(1); });
