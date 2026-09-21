/* Verifica il caricamento di un set di pezzi dal dispositivo (app/pieceset.js).

   I file di prova sono generati dal chiamante: nel repo non entra nessun set,
   ne' libero ne' commerciale. Gira su WebKit perche' il bersaglio e' l'iPhone
   e IndexedDB e' il punto delicato. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {webkit} = require('playwright');

const DIR = process.env.PIECESET_DIR;
const URL_ = process.env.BOOK_TEST_URL || 'http://localhost:8765/';

(async () => {
  if(!DIR){ console.error('PIECESET_DIR non impostata'); process.exit(2); }
  const files = fs.readdirSync(DIR).map(f => `${DIR}/${f}`);
  const browser = await webkit.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    await page.goto(URL_, {waitUntil: 'domcontentloaded'});
    await page.waitForSelector('.pieceset button');

    const chooser = page.waitForEvent('filechooser');
    await page.click('.pieceset button');
    await (await chooser).setFiles(files);
    await page.waitForFunction(() => !!customPieces);

    // Dalla home si passa a una scacchiera vera: le immagini devono essere
    // quelle caricate, non quelle del pacchetto.
    await page.click('[data-nav="puzzles"]');
    await page.click('#puzzleMixed');
    await page.waitForSelector('#board .piece img');
    const srcs = await page.$$eval('#board .piece img', els => els.map(e => e.getAttribute('src')));
    assert.ok(srcs.length > 0, 'nessun pezzo disegnato');
    assert.ok(srcs.every(s => s.startsWith('data:image/')), 'la scacchiera usa ancora il set di serie');

    // Il set deve sopravvivere al riavvio dell'app
    await page.reload({waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => !!customPieces);
    await page.waitForSelector('.pieceset button');
    const back = await page.$$eval('.pieceset button', els => els.map(e => e.textContent.trim()));
    assert.ok(back.some(t => /predefinito/i.test(t)), 'manca il ritorno al set di serie');

    await page.click('.pieceset button:nth-of-type(2)');
    await page.waitForFunction(() => !customPieces);
    assert.deepEqual(errors, [], 'errori JS in pagina');
    console.log('OK · import, uso sulla scacchiera, persistenza, ritorno al set di serie');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error('FALLITO:', e.message); process.exit(1); });
