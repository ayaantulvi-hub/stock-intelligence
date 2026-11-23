// SYNTHETIC DEMO ONLY: screenshots of a local dashboard running on demo/ data, with a red banner
// saying so. Run with the API on port 8000 and `npx vite` on port 5173.
const { chromium } = require('playwright');
const OUT = require('path').join(__dirname, '..', 'docs', 'screenshots');
const BANNER = `const b=document.createElement('div');b.textContent='SYNTHETIC DEMO DATA: invented companies and random prices, not real results';Object.assign(b.style,{position:'fixed',bottom:'0',left:'0',right:'0',zIndex:99999,background:'#b00020',color:'#fff',font:'600 14px system-ui',padding:'6px 12px',textAlign:'center'});document.body.appendChild(b);`;
(async () => {
  const browser = await chromium.launch();
  const shots = [
    ['quant-lab-overview.png', '#overview'],
    ['quant-lab-pairs.png', '#pairs_trading'],
    ['quant-lab-var-quant.png', '#value_at_risk', 'Quant detail'],
  ];
  for (const [file, hash, button] of shots) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
    await page.goto(`http://localhost:5173/${hash}`, { waitUntil: 'networkidle' });
    if (button) await page.getByRole('radio', { name: button }).click();
    await page.waitForTimeout(1800);
    await page.evaluate(BANNER);
    await page.screenshot({ path: `${OUT}/${file}`, fullPage: true });
    await page.close();
  }
  await browser.close();
})();
