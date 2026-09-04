import fs from 'node:fs';
import { openBrowser, ensureBrowser } from '@remotion/renderer';

// Mỗi ảnh gắn với một TỪ KHÓA thật sự được nói trong kịch bản.
const SHOTS = [
  { name: 'claude-code', url: 'https://www.claude.com/product/claude-code' },
];

// Ẩn banner cookie/consent bằng CSS — KHÔNG bấm đồng ý, không gửi lựa chọn nào đi
const HIDE = `
  (() => {
    const pat = /cookie|consent|gdpr|banner|newsletter|modal|overlay|backdrop|dialog/i;
    let n = 0;
    document.querySelectorAll('div,section,aside,dialog').forEach((e) => {
      const id = (e.id || '') + ' ' + (e.className && e.className.toString ? e.className.toString() : '');
      const st = getComputedStyle(e);
      if (pat.test(id) && (st.position === 'fixed' || st.position === 'sticky')) { e.style.display = 'none'; n++; }
    });
    document.querySelectorAll('*').forEach((e) => {
      const st = getComputedStyle(e);
      if (st.position === 'fixed' && parseInt(st.zIndex || '0', 10) > 900 && e.offsetHeight > 60) { e.style.display = 'none'; n++; }
    });
    return n;
  })()
`;

// Khung hẹp hơn => nội dung trang to hơn trong ảnh, đọc rõ trên điện thoại
const VW = 1180, VH = 760;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await ensureBrowser();
const browser = await openBrowser('chrome');
fs.mkdirSync('public/shots', { recursive: true });

for (const [i, s] of SHOTS.entries()) {
  const page = await browser.newPage({ logLevel: 'error', indent: false, pageIndex: i });
  const client = page._client();
  try {
    await page.setViewport({ width: VW, height: VH, deviceScaleFactor: 2 });
    await page.goto({ url: s.url, timeout: 45000 });
    await sleep(4200);
    await client.send('Runtime.evaluate', { expression: HIDE, returnByValue: true });
    await sleep(700);
    const r = await client.send('Page.captureScreenshot', { format: 'png' });
    const out = `public/shots/${s.name}.png`;
    fs.writeFileSync(out, Buffer.from(r.value.data, 'base64'));
    const kb = fs.statSync(out).size / 1024;
    console.log(`${kb < 60 ? '?' : '✓'} ${s.name.padEnd(14)} ${kb.toFixed(0).padStart(5)} KB  ${s.url}`);
  } catch (e) {
    console.log(`✗ ${s.name.padEnd(14)}       ${e.message.slice(0, 70)}`);
  }
  await page.close();
}
await browser.close({ silent: true });
console.log('\n(? = file nhỏ bất thường, nhiều khả năng bị chặn hoặc trang trắng — phải mở xem)');
