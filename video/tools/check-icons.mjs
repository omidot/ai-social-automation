import fs from 'node:fs';
const tl = JSON.parse(fs.readFileSync('src/timeline.json', 'utf8'));
const ic = fs.readFileSync('src/icons.tsx', 'utf8');
const names = [...ic.matchAll(/^\s{2}([a-z0-9]+):\s*\{/gm)].map((m) => m[1]);
console.log('icon có sẵn:', names.join(', '));
const secs = [...new Set(tl.cards.map((c) => c.section))];
let bad = 0;
for (const s of secs) {
  const i = ic.indexOf(`'${s}':`);
  const val = i < 0 ? null : ic.slice(i + s.length + 3).match(/'([a-z0-9]+)'/)?.[1];
  const ok = val && names.includes(val);
  if (!ok) bad++;
  console.log(`  ${ok ? '✓' : '✗'} ${String(val ?? 'THIẾU').padEnd(8)} ${s}`);
}
console.log(bad ? `\n${bad} chương thiếu icon` : '\nđủ icon cho mọi chương');
