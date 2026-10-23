// 把 tools/mocks.html 裡每個 .mock 存成 img/<id>.png。用法：node tools/mocks.cjs（要先有 puppeteer-core 和 Chrome）
const path = require('path');
const puppeteer = require(process.env.PUPPETEER || '/Users/hermes/Public/0720/office-reel/node_modules/puppeteer-core');
(async () => {
  const b = await puppeteer.launch({headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const pg = await b.newPage();
  await pg.setViewport({width: 1040, height: 800, deviceScaleFactor: 1.5});
  await pg.goto('file://' + path.join(__dirname, 'mocks.html'));
  await pg.evaluateHandle('document.fonts.ready');
  for (const el of await pg.$$('.mock')) {
    const id = await el.evaluate(e => e.id);
    await el.screenshot({path: path.join(__dirname, '..', 'img', id + '.png')});
    console.log(id);
  }
  await b.close();
})();
