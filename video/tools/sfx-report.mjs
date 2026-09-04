import fs from 'node:fs';
const tl = JSON.parse(fs.readFileSync('src/timeline.json', 'utf8'));
const MOT = { rise: 'm-rise', fall: 'm-fall', slideL: 'u-whoosh', pop: 'm-pop', slam: 'u-impact2' };
const c = {}; const bump = (k, n = 1) => { c[k] = (c[k] || 0) + n; };
let tickN = 0, lineTicks = 0, cardTicks = 0;
tl.cards.forEach((x) => {
  const m = MOT[x.motion];
  if (m) bump(m); else { bump(tickN % 2 ? 't-key' : 't-blip'); tickN++; cardTicks++; }
  const v = x.lines.filter((l) => !l.hidden);
  for (let i = 1; i < v.length; i++) { bump(tickN % 2 ? 't-key' : 't-blip'); tickN++; lineTicks++; }
});
bump('u-impact', tl.cards.filter((x) => x.variant === 'invert').length);
bump('u-riser', 1); bump('u-drone', 3); bump('type', 2); bump('swipe', 6); bump('u-click', 6);
const total = Object.values(c).reduce((a, b) => a + b, 0);
console.log(`${Object.keys(c).length} âm khác nhau · ${total} điểm\n`);
Object.entries(c).sort((a, b) => b[1] - a[1]).forEach(([k, n]) => {
  console.log(`  ${fs.existsSync(`public/sfx/${k}.mp3`) ? '✓' : '✗ THIẾU'} ${k.padEnd(12)} ${String(n).padStart(3)}`);
});
console.log(`\n  tick: ${cardTicks} card (3 kiểu bị bỏ âm) + ${lineTicks} dòng phụ = ${cardTicks + lineTicks}`);
console.log(`  tổng dòng chữ có tiếng: ${tl.cards.length + lineTicks}`);
