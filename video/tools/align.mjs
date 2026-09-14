import fs from 'node:fs';
import { CARDS, SECTIONS } from './cards.mjs';
import { LAYOUT } from './variants.mjs';

const FPS = 30;
const DURATION = Number(process.argv[2] ?? 136.803265);

// ---- 0. Mốc thời gian THẬT (nhận diện giọng nói), nếu có ----
// transcribe.py ghi ref/words.json khi nhận diện thành công. Không có file
// này (chưa cài model, nhận diện lỗi, ...) -> rơi về ước lượng khoảng lặng
// ở dưới, y như trước.
let realWords = null;
try {
  const parsed = JSON.parse(fs.readFileSync('ref/words.json', 'utf8'));
  if (Array.isArray(parsed) && parsed.length > 0) realWords = parsed;
} catch { /* không có file hoặc lỗi đọc -> dùng ước lượng khoảng lặng */ }

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
// unit sở hữu từng từ, cùng thứ tự với allWords -- dùng ở bước 4c
const wordUnit = [];
units.forEach((u, ui) => u.words.forEach(() => wordUnit.push(ui)));
const totalWeight = allWords.reduce((a, x) => a + x.weight, 0);

// ---- 4. Gán mốc thời gian cho từng từ trong kịch bản ----
// Chuẩn hoá để so khớp: bỏ dấu tiếng Việt + dấu câu, viết thường. ASR và
// kịch bản không khớp chữ 100% (lỗi nhận diện, khác cách viết hoa...) nên
// so khớp "gần đúng" theo hình dạng chữ cái, không so khớp tuyệt đối.
const COMBINING_MARKS = new RegExp('[̀-ͯ]', 'g');
const norm = (s) => s.toLowerCase().replace(/đ/g, 'd').normalize('NFD')
  .replace(COMBINING_MARKS, '').replace(/[^\p{L}\p{N}]/gu, '');

/** Căn chuỗi kịch bản (a) với chuỗi ASR (b) bằng quy hoạch động (Needleman-Wunsch).
 *  Trả về map[i] = j (từ ASR khớp với từ kịch bản thứ i) hoặc null nếu ASR bỏ sót. */
function alignWords(a, b) {
  const n = a.length, m = b.length;
  const na = a.map(norm), nb = b.map(norm);
  const dp = Array.from({ length: n + 1 }, () => new Float64Array(m + 1));
  for (let i = 0; i <= n; i++) dp[i][0] = i;
  for (let j = 0; j <= m; j++) dp[0][j] = j;
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      const sub = dp[i - 1][j - 1] + (na[i - 1] === nb[j - 1] && na[i - 1] !== '' ? 0 : 1);
      dp[i][j] = Math.min(sub, dp[i - 1][j] + 1, dp[i][j - 1] + 1);
    }
  }
  const map = new Array(n).fill(null);
  let i = n, j = m;
  while (i > 0 && j > 0) {
    const sub = dp[i - 1][j - 1] + (na[i - 1] === nb[j - 1] && na[i - 1] !== '' ? 0 : 1);
    if (dp[i][j] === sub) { map[i - 1] = j - 1; i--; j--; }
    else if (dp[i][j] === dp[i - 1][j] + 1) { i--; }
    else { j--; }
  }
  return map;
}

/** Gán start/end từ mốc ASR thật; trả về null nếu tỉ lệ khớp quá thấp
 *  (giọng đọc lệch quá xa kịch bản) để rơi về ước lượng khoảng lặng.
 *  Khi thành công trả về map để bước 4c thay chữ hiển thị bằng lời nói thật. */
function assignFromRealWords(words, real) {
  const map = alignWords(words.map((w) => w.w), real.map((w) => w.w));
  const matched = map.filter((x) => x !== null).length;
  if (words.length === 0 || matched / words.length < 0.4) return null;
  for (let i = 0; i < words.length; i++) {
    if (map[i] !== null) { words[i].start = real[map[i]].start; words[i].end = real[map[i]].end; }
  }
  let i = 0;
  while (i < words.length) {
    if (words[i].start !== undefined) { i++; continue; }
    let j = i;
    while (j < words.length && words[j].start === undefined) j++;
    const prevEnd = i > 0 ? words[i - 1].end : 0;
    const nextStart = j < words.length ? words[j].start : prevEnd + (j - i) * 0.3;
    const span = Math.max(nextStart - prevEnd, 0.05 * (j - i));
    for (let k = i; k < j; k++) {
      words[k].start = prevEnd + (span * (k - i)) / (j - i);
      words[k].end = prevEnd + (span * (k - i + 1)) / (j - i);
    }
    i = j;
  }
  return map;
}

const wordMap = realWords ? assignFromRealWords(allWords, realWords) : null;
const usedRealWords = wordMap !== null;

// ---- 4b. Không có (hoặc không dùng được) mốc thật -> rải từ theo khoảng lặng ----
if (!usedRealWords) {
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
}

// ---- 4c. Chữ hiển thị = ĐÚNG LỜI NÓI, không phải chữ trong kịch bản ----
// Người đọc hiếm khi đọc y nguyên từng chữ kịch bản (đọc diễn giải, thêm/bớt
// từ, đổi cách nói). Nếu vẫn hiện chữ kịch bản thì dù canh nhịp chuẩn, chữ
// trên màn hình vẫn không trùng lời nói. Nên ở đây ta thay hẳn chữ hiển thị
// bằng chuỗi từ ASR, giữ nguyên cách chia card của kịch bản.
const MAX_LINE_CHARS = 26;   // đủ to để đọc trên điện thoại ở khung dọc 1080
const LINES_PER_CARD = 3;    // quá số này thì chữ bị co nhỏ, khó đọc

/** Gói chuỗi từ thành các dòng không quá MAX_LINE_CHARS ký tự. */
function packLines(ws) {
  const groups = [];
  let cur = [], len = 0;
  for (const w of ws) {
    const add = w.text.length + (cur.length ? 1 : 0);
    if (cur.length && len + add > MAX_LINE_CHARS) { groups.push(cur); cur = []; len = 0; }
    cur.push(w); len += add;
  }
  if (cur.length) groups.push(cur);
  return groups.map((g) => ({
    text: g.map((x) => x.text).join(' '),
    start: g[0].start, end: g[g.length - 1].end, hidden: false, words: g,
  }));
}

// ---- 5. Gộp lên mức dòng rồi mức card ----
for (const u of units) { u.start = u.words[0].start; u.end = u.words[u.words.length - 1].end; }

let cards;
let srcOf;   // card mới -> dòng LAYOUT/section gốc của kịch bản
if (usedRealWords) {
  // Lời nói thật thường nhiều chữ hơn kịch bản (kịch bản là bản rút gọn để
  // chạy chữ). Nhồi lời nói vào đúng khung card cũ sẽ ra những card cả chục
  // dòng, chữ co lại không đọc nổi -- nên chia lại card theo chính lời nói,
  // rồi ánh xạ kiểu dáng của kịch bản lên theo tỉ lệ để giữ mạch thiết kế.
  const lines = packLines(realWords.map((r) => ({ text: r.w, start: r.start, end: r.end })));
  const groups = [];
  for (let i = 0; i < lines.length; i += LINES_PER_CARD) groups.push(lines.slice(i, i + LINES_PER_CARD));
  cards = groups.map((g, k) => ({
    index: k, lines: g, start: g[0].start, end: g[g.length - 1].end,
  }));
  srcOf = (k) => Math.min(CARDS.length - 1, Math.floor((k * CARDS.length) / cards.length));
} else {
  cards = CARDS.map((lines, ci) => {
    const mine = units.filter((u) => u.card === ci);
    return {
      index: ci,
      lines: mine.map((u) => ({
        text: u.text, start: u.start, end: u.end, hidden: u.hidden,
        // mốc từng TỪ riêng lẻ -- để chữ hiện ra đúng lúc giọng đọc tới, không
        // phải cả dòng hiện cùng lúc rồi mới tô sáng dòng đang nói.
        words: u.words.map((w) => ({ text: w.w, start: w.start, end: w.end })),
      })),
      start: mine[0].start, end: mine[mine.length - 1].end,
    };
  });
  srcOf = (k) => k;
}
// card sống tới khi card sau bắt đầu -> không có khoảng trống trắng
cards.forEach((c, i) => { c.out = i < cards.length - 1 ? cards[i + 1].start : DURATION; });

const sectionFor = (ci) => { let lbl = SECTIONS[0][1]; for (const [at, l] of SECTIONS) if (ci >= at) lbl = l; return lbl; };
// biểu đồ / ảnh chụp chỉ gắn vào card ĐẦU TIÊN ánh xạ về dòng LAYOUT đó,
// nếu không sẽ bị lặp lại trên nhiều card liền nhau.
const usedSrc = new Set();
cards.forEach((c) => {
  const si = srcOf(c.index);
  const first = !usedSrc.has(si);
  usedSrc.add(si);
  c.section = sectionFor(si);
  const [v, a, n, mi, mo, ch, sf, su] = LAYOUT[si];
  c.variant = v; c.anchor = a; c.motion = mi; c.exit = mo;
  if (n && first) c.num = n;
  if (ch && first) c.chart = ch;
  if (sf && first) c.screenshotFile = sf;
  if (su && first) c.screenshotUrl = su;
});

const out = { fps: FPS, duration: DURATION, durationInFrames: Math.ceil(DURATION * FPS) + 18, cards };
fs.writeFileSync('src/timeline.json', JSON.stringify(out, null, 1));

// ---- 6. Báo cáo ----
console.log(usedRealWords
  ? `canh chữ: dùng mốc THẬT từ nhận diện giọng nói (${realWords.length} từ ASR)`
  : `canh chữ: dùng ước lượng khoảng lặng (không có/không dùng được ref/words.json)`);
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
