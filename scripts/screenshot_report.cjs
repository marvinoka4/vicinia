// Save screenshots of the static HTML report to docs/img.
// Optional helper: needs Node.js and the playwright package with Chromium.
// Usage: node scripts/screenshot_report.cjs results/report.html docs/img
const { chromium } = require("playwright");
const { mkdirSync } = require("node:fs");
const { resolve } = require("node:path");

const [src = "results/report.html", outDir = "docs/img"] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const url = "file://" + resolve(src);
(async () => {
const browser = await chromium.launch();

const shots = [
  { name: "report_top.png", width: 1200, height: 900, scheme: "light", full: false },
  { name: "report_full.png", width: 1200, height: 900, scheme: "light", full: true },
  { name: "report_dark.png", width: 1200, height: 900, scheme: "dark", full: false },
  { name: "report_mobile.png", width: 390, height: 844, scheme: "light", full: false },
];
for (const s of shots) {
  const page = await browser.newPage({ viewport: { width: s.width, height: s.height }, colorScheme: s.scheme });
  await page.goto(url);
  await page.screenshot({ path: `${outDir}/${s.name}`, fullPage: s.full });
  await page.close();
}
await browser.close();
console.log(`wrote ${shots.length} screenshots to ${outDir}`);
})();
