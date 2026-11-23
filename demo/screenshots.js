// SYNTHETIC DEMO ONLY: screenshots of a local dashboard running on demo/ data, with a red banner.
// Source labels are replaced with 'SYNTHETIC demo data' so no fake number is credited to a real source.
const { chromium } = require('playwright');
const OUT = require('path').join(__dirname, '..', 'docs', 'screenshots');
const BANNER = `const b=document.createElement('div');b.textContent='SYNTHETIC DEMO DATA: invented companies and random prices, not real market data';Object.assign(b.style,{position:'fixed',top:'0',left:'0',right:'0',zIndex:99999,background:'#b00020',color:'#fff',font:'600 14px system-ui',padding:'6px 12px',textAlign:'center'});document.body.appendChild(b);const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while((n=w.nextNode())){if(/via FRED|Federal Reserve|Tiingo|Baker, Bloom/.test(n.nodeValue)&&!/FRED® API/.test(n.nodeValue)){n.nodeValue='SYNTHETIC demo data';}}document.body.style.paddingTop='32px';`;
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
  const pages = ['Trading', 'Long-term', 'My portfolio', 'How reliable?', 'Data'];
  for (const [i, name] of pages.entries()) {
    await page.getByRole('button', { name, exact: true }).first().click();
    await page.waitForLoadState('networkidle'); await page.waitForTimeout(1500);
    await page.evaluate(BANNER);
    await page.screenshot({ path: `${OUT}/${i + 1}-${name.toLowerCase().replace(/[^a-z]+/g, '-').replace(/-$/, '')}.png`, fullPage: true });
    await page.evaluate(() => { document.querySelectorAll('div').forEach(d => { if (d.textContent.startsWith('SYNTHETIC DEMO DATA') && d.style.position === 'fixed') d.remove(); }); });
  }
  const box = page.getByRole('searchbox').or(page.locator('input[type=search], header input')).first();
  await box.fill('DMAL0'); await box.press('Enter');
  await page.waitForLoadState('networkidle'); await page.waitForTimeout(1500);
  await page.getByRole('button', { name: 'DMAL0' }).first().click().catch(() => page.getByText('DMAL0').first().click());
  await page.waitForLoadState('networkidle');
  await page.waitForFunction(() => !document.body.innerText.includes('Checking…') && !document.body.innerText.includes('Checking...'), null, { timeout: 60000 }).catch(() => console.log('still checking'));
  await page.waitForTimeout(1500);
  await page.evaluate(BANNER);
  await page.screenshot({ path: `${OUT}/6-stock-page.png`, fullPage: true });
  console.log('errors', errors);
  await browser.close();
})();
