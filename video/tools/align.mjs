import fs from 'node:fs';
import { CARDS, SECTIONS } from './cards.mjs';
import { LAYOUT } from './variants.mjs';

const FPS = 30;
const DURATION = Number(process.argv[2] ?? 136.803265);

// ---- 1. Đọc các khoảng lặng do ffmpeg silencedetect tìm ra ----
const raw = fs.readFileSync('ref/silence.txt', 'utf8');
const silences = [];
let cur = null;
for (const line of raw.split(/\r?\n/)) {
  const s = line.match(/silence_start:\s*([\d.]+)/);
  const e = line.match(/silence_end:\s*([\d.]+)/);
  if (s) cur = { start: Number(s[1]) };
  if (e && cur) { cur.end = Number(e[1]); silences.push(cur); cur = null; }
}
if (cur) silences.push({ ...cur, end: DURATION });

// ---- 2. Đảo thành các đoạn CÓ TIẾNG ----
const speech = [];
let t = 0;
for (const s of silences) {
  if (s.start > t + 0.03) speech.push([t, s.start]);
  t = s.end;
}
if (t < DURATION - 0.03) speech.push([t, DURATION]);
const totalSpeech = speech.reduce((a, [x, y]) => a + (y - x), 0);

// ---- 3. Dòng chữ -> chuỗi từ, có trọng số theo độ dài ----
const units = [];  // {card, line, words:[{w,weight}]}
CARDS.forEach((lines, ci) => lines.forEach((raw, li) => {
  const hidden = raw.startsWith('~');
  const text = hidden ? raw.slice(1) : raw;
  const words = text.split(/\s+/).filter(Boolean).map((w) => ({
    w,
    // âm tiết dài + dấu câu cuối câu = đọc lâu hơn
    weight: Math.max(1, w.replace(/[^\p{L}\p{N}]/gu, '').length * 0.42) + (/[.,:?!]$/.test(w) ? 0.9 : 0),
  }));
  units.push({ card: ci, line: li, text, hidden, words });
}));
// Dòng ẩn nằm ở ĐẦU card sẽ để màn hình trống cho tới khi dòng hiện đầu tiên tới.
// Đẩy chúng về cuối card trước — card trước sống thêm, không có khoảng trắng.
for (let ci = 1; ci < CARDS.length; ci++) {
  const mine = units.filter((u) => u.card === ci);
  for (const u of mine) {
    if (!u.hidden) break;
    if (mine.filter((x) => x.card === ci).length <= 1) break; // đừng làm rỗng card
    u.card = ci - 1;
  }
}

const allWords = units.flatMap((u) => u.words);
const totalWeight = allWords.reduce((a, x) => a + x.weight, 0);

// ---- 4. Rải từ vào các đoạn có tiếng, tỷ lệ theo trọng số ----
let wi = 0, carried = 0;
for (let si = 0; si < speech.length; si++) {
  const [s0, s1] = speech[si];
  const isLast = si === speech.length - 1;
  let quota = (totalWeight * (s1 - s0)) / totalSpeech + carried;
  const bucket = [];
  let used = 0;
  while (wi < allWords.length && (used < quota || (isLast && wi < allWords.length))) {
    bucket.push(allWords[wi]); used += allWords[wi].weight; wi++;
  }
  carried = quota - used;
  const sum = bucket.reduce((a, x) => a + x.weight, 0) || 1;
  let acc = 0;
  for (const w of bucket) {
    w.start = s0 + ((s1 - s0) * acc) / sum;
    acc += w.weight;
    w.end = s0 + ((s1 - s0) * acc) / sum;
  }
}
// từ nào chưa được gán (phòng hờ) -> dính vào cuối
for (const w of allWords) if (w.start === undefined) { w.start = DURATION - 0.2; w.end = DURATION; }

// ---- 5. Gộp lên mức dòng rồi mức card ----
for (const u of units) { u.start = u.words[0].start; u.end = u.words[u.words.length - 1].end; }
const cards = CARDS.map((lines, ci) => {
  const mine = units.filter((u) => u.card === ci);
  return { index: ci, lines: mine.map((u) => ({ text: u.text, start: u.start, end: u.end, hidden: u.hidden })), start: mine[0].start, end: mine[mine.length - 1].end };
});
// card sống tới khi card sau bắt đầu -> không có khoảng trống trắng
cards.forEach((c, i) => { c.out = i < cards.length - 1 ? cards[i + 1].start : DURATION; });

const sectionFor = (ci) => { let lbl = SECTIONS[0][1]; for (const [at, l] of SECTIONS) if (ci >= at) lbl = l; return lbl; };
cards.forEach((c) => { c.section = sectionFor(c.index); const [v, a, n, mi, mo] = LAYOUT[c.index]; c.variant = v; c.anchor = a; c.motion = mi; c.exit = mo; if (n) c.num = n; });

const out = { fps: FPS, duration: DURATION, durationInFrames: Math.ceil(DURATION * FPS) + 18, cards };
fs.writeFileSync('src/timeline.json', JSON.stringify(out, null, 1));

// ---- 6. Báo cáo ----
console.log(`đoạn có tiếng: ${speech.length} | tổng ${totalSpeech.toFixed(1)}s / ${DURATION.toFixed(1)}s`);
console.log(`card: ${cards.length} | dòng: ${units.length} | từ: ${allWords.length}`);
const durs = cards.map((c) => c.out - c.start);
console.log(`card ngắn nhất ${Math.min(...durs).toFixed(2)}s | dài nhất ${Math.max(...durs).toFixed(2)}s | trung bình ${(durs.reduce((a,b)=>a+b,0)/durs.length).toFixed(2)}s`);

// đo thời gian mỗi dòng HIỆN nằm trên màn hình
const holds = [];
cards.forEach((c) => c.lines.forEach((l) => { if (!l.hidden) holds.push({ t: l.text, h: c.out - l.start }); }));
holds.sort((a, b) => a.h - b.h);
const N = holds.length, q = (p) => holds[Math.floor(N * p)].h.toFixed(2);
console.log(`dòng HIỆN: ${N} | dòng ẩn giữ giờ: ${units.length - N}`);
console.log(`  nằm trên màn hình — ngắn nhất ${holds[0].h.toFixed(2)}s | 25%: ${q(0.25)}s | giữa: ${q(0.5)}s | 75%: ${q(0.75)}s`);
console.log(`  dưới 1.2s: ${holds.filter((x) => x.h < 1.2).length} | dưới 1.5s: ${holds.filter((x) => x.h < 1.5).length}`);
console.log('  nhanh nhất:', holds.slice(0, 4).map((x) => x.h.toFixed(2) + 's "' + x.t + '"').join('  '));
