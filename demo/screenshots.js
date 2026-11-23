// SYNTHETIC DEMO ONLY: screenshots of a local dashboard running on demo/ data, with a red banner
// saying so. Run with the API on port 8000 and `npx vite` on port 5173.
const { chromium } = require('playwright');
const OUT = require('path').join(__dirname, '..', 'docs', 'screenshots');
const BANNER = `const b=document.createElement('div');b.textContent='SYNTHETIC DEMO DATA: invented companies and random prices, not real results';Object.assign(b.style,{position:'fixed',bottom:'0',left:'0',right:'0',zIndex:99999,background:'#b00020',color:'#fff',font:'600 14px system-ui',padding:'6px 12px',textAlign:'center'});document.body.appendChild(b);`;
(async () => {
  const browser = await chromium.launch();
  const shots = [
    ['quant-lab-desktop.png', { viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 }, true],
    ['quant-lab-phone.png', { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 }, false],
  ];
  for (const [file, options, full] of shots) {
    const page = await browser.newPage(options);
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await page.evaluate(BANNER);
    await page.screenshot({ path: `${OUT}/${file}`, fullPage: full });
    await page.close();
  }
  await browser.close();
})();
