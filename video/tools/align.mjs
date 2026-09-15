import fs from 'node:fs';
import { CARDS, SECTIONS } from './cards.mjs';
import { LAYOUT } from './variants.mjs';
import { chartsFromSpeech } from './autoviz.mjs';
import { buildTimeline } from './screens.mjs';
import { pickElementKind } from './elementpick.mjs';
import { cardsFromText } from './listcards.mjs';

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

// ---- 4c. (đã gỡ) Sửa tên thương hiệu bị nghe nhầm ----
// Trước đây màn hình hiện thẳng chữ NHẬN DIỆN được, nên tên riêng bị máy
// nghe sai ("Fable" -> "Facebook", "Claude" -> "Cloud") lên hình là sai
// luôn thương hiệu, phải có một lớp dò tìm và sửa lại bằng khoảng cách
// Levenshtein. Giờ màn hình hiện chữ của KỊCH BẢN (xem bước 5), nên mọi
// tên riêng vốn đã đúng chính tả từ đầu -- cả lớp sửa đó thành thừa và
// được gỡ bỏ thay vì để lại làm chỗ sinh lỗi.

// Bản tham chiếu chỉ để 2-4 từ dưới đáy mỗi lúc ("phục vụ được nhiều,",
// "ở giờ thấp điểm."). Dài hơn là mắt phải đọc thay vì nghe.
const MAX_LINE_CHARS = 22;
const LINES_PER_CARD = 1;    // một dòng một lúc, đúng như bản tham chiếu

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
    src: g[0].src,
  }));
}

// ---- 5. Gộp lên mức dòng rồi mức card ----
for (const u of units) { u.start = u.words[0].start; u.end = u.words[u.words.length - 1].end; }

let cards;
let srcOf;   // card mới -> dòng LAYOUT/section gốc của kịch bản
if (usedRealWords) {
  // CHỮ lấy từ KỊCH BẢN, GIỜ lấy từ GIỌNG NÓI THẬT.
  //
  // Hiển thị thẳng chữ nhận diện được thì đúng giờ nhưng sai chính tả:
  // máy nghe "Perplexity" ra "Proplexity", "GPT-6" ra "GP6", "giỏi hơn"
  // ra "rõi hơn" -- chữ sai chính tả đập vào mặt người xem suốt video.
  // Ngược lại, lấy chữ kịch bản rồi tự đoán giờ thì chữ chạy lệch tiếng
  // nói cả chục giây.
  //
  // Bước 4 đã căn từng từ kịch bản vào đúng mốc giờ của từ tương ứng
  // trong giọng đọc, nên ở đây dùng được cả hai: chữ chuẩn của kịch bản,
  // đặt đúng giây nó được nói ra.
  const visible = [];
  allWords.forEach((w, i) => {
    const u = units[wordUnit[i]];
    if (u.hidden) return;                     // dòng "~" chỉ giữ chỗ tính giờ
    visible.push({ text: w.w, start: w.start, end: w.end, src: u.card });
  });
  const lines = packLines(visible);
  const groups = [];
  for (let i = 0; i < lines.length; i += LINES_PER_CARD) groups.push(lines.slice(i, i + LINES_PER_CARD));
  cards = groups.map((g, k) => ({
    index: k, lines: g, start: g[0].start, end: g[g.length - 1].end,
    src: g[0].src,
  }));
  // Ánh xạ CHÍNH XÁC về card kịch bản gốc (qua unit sở hữu từ đầu dòng),
  // không phải chia đều theo tỉ lệ như trước -- nhờ vậy biểu đồ/ảnh gắn
  // đúng đoạn nội dung của nó.
  srcOf = (k) => Math.min(CARDS.length - 1, cards[k].src ?? 0);
} else {
  cards = CARDS.map((lines, ci) => {
    const mine = units.filter((u) => u.card === ci);
    return {
      index: ci,
      lines: mine.map((u) => ({
        text: u.text, start: u.start, end: u.end, hidden: u.hidden,
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

// Hình minh hoạ (biểu đồ / ảnh chụp / tiêu đề) phải ĐỨNG NGUYÊN suốt cả
// đoạn kịch bản, y như bản tham chiếu: hình nói CHỦ ĐỀ, caption dưới chạy
// theo lời nói. Trước đây chỉ gắn vào card ĐẦU TIÊN ánh xạ về dòng LAYOUT
// đó, nên một biểu đồ chỉ loé lên 2-3 giây rồi cả chục card sau trống đen.
// Gắn cho MỌI card cùng nguồn, kèm visualAt = mốc card đầu của nhóm để
// hiệu ứng dựng hình không chạy lại từ đầu mỗi lần sang card mới.
const groupStart = new Map();   // si -> start của card đầu tiên thuộc nhóm
cards.forEach((c) => {
  const si = srcOf(c.index);
  if (!groupStart.has(si)) groupStart.set(si, c.start);
});

cards.forEach((c) => {
  const si = srcOf(c.index);
  c.section = sectionFor(si);
  const [v, a, n, mi, mo, ch, sf, su] = LAYOUT[si];
  c.variant = v; c.anchor = a; c.motion = mi; c.exit = mo;
  c.visualAt = groupStart.get(si);
  if (n) c.num = n;
  if (ch) c.chart = ch;
  if (sf) c.screenshotFile = sf;
  if (su) c.screenshotUrl = su;
  // Tiêu đề TO phía trên = chữ KỊCH BẢN của card gốc, đứng yên suốt cả
  // đoạn (không chạy theo từng từ).
  c.headline = CARDS[si].map((raw) => (raw.startsWith('~') ? raw.slice(1) : raw))
    .filter(Boolean);
  c.headlineAt = si;
});

// ---- 5b. Biểu đồ dựng TỪ CHÍNH LỜI NÓI ----
// Chờ mô hình viết kịch bản gắn thẻ 'chart' là không ăn thua: đo thật chỉ
// 1 biểu đồ trên 38 card, trong khi giọng đọc đọc ra đầy số liệu ("Gói Plus
// 45 tin, Gói Pro 100 đô 225 tin, Gói Pro 200 đô 900 tin") mà màn hình để
// trống. autoviz đọc thẳng bản ghi lời nói và dựng biểu đồ đúng giây con số
// được nói ra. Số liệu cắt từ lời nói nên không có chuyện bịa.
let autoCharts = [];
if (usedRealWords) {
  try {
    // Dùng chữ KỊCH BẢN (đã mang mốc giờ thật) chứ không dùng chữ nhận
    // diện: nhãn biểu đồ cũng phải đúng chính tả như caption.
    autoCharts = chartsFromSpeech(
      allWords.map((w) => ({ w: w.w, start: w.start, end: w.end })));
    // Kịch bản đôi khi đã tự gắn biểu đồ cho chính những con số đó. Dựng
    // thêm một cái nữa là cùng một bảng số hiện hai lần cách nhau vài giây
    // (đo thật: 90.7s và 94.3s cùng là 45/225/900). Giữ bản của KỊCH BẢN
    // vì nó có nhãn do người viết đặt, bỏ bản tự dựng trùng nó.
    const valueKey = (items) => items.map((i) => i.value).sort((a, b) => a - b).join('|');
    const scripted = cards
      .filter((c) => c.chart && c.chart.items && c.chart.items.length)
      .map((c) => ({ key: valueKey(c.chart.items), at: c.visualAt ?? c.start }));
    const DUP_WINDOW = 20;   // giây

    for (const ac of autoCharts) {
      const key = valueKey(ac.items);
      const dup = scripted.some((s) => s.key === key && Math.abs(s.at - ac.start) <= DUP_WINDOW);
      if (dup) continue;
      for (const c of cards) {
        // phủ lên mọi card nằm trong khoảng con số đang được nói
        if (c.out <= ac.start || c.start >= ac.end) continue;
        if (c.screenshotFile) continue;        // ảnh chụp đã chiếm cả khung
        if (c.chart) continue;                 // kịch bản đã có hình cho đoạn này
        c.chart = { kind: ac.kind, items: ac.items, unit: ac.unit, title: ac.title };
        c.visualAt = ac.start;
        c.num = undefined;
      }
    }
  } catch (e) {
    console.log(`autoviz lỗi, bỏ qua: ${e.message}`);
  }
}

// ---- 5c. Giữ hình trên màn hình cho tới khi có hình khác ----
// Bản tham chiếu để một tấm số liệu đứng yên cả chục giây trong khi caption
// chạy bên dưới. Nếu chỉ hiện đúng khoảng câu nói chứa con số thì hình loé
// vài giây rồi cả đoạn sau lại là khung trống (đo thật: 5% thời lượng có
// hình). Mỗi hình được kéo dài tới khi hình KHÁC bắt đầu, tối đa HOLD giây.
const HOLD = 14;
{
  const sig = (c) => (c.screenshotFile ? `s:${c.screenshotFile}`
    : c.chart ? `c:${JSON.stringify(c.chart)}` : '');
  for (let i = 0; i < cards.length; i++) {
    const src = cards[i];
    if (!src.chart && !src.screenshotFile) continue;
    const mine = sig(src);
    const until = (src.visualAt ?? src.start) + HOLD;
    for (let j = i + 1; j < cards.length; j++) {
      const c = cards[j];
      if (sig(c) === mine) continue;            // vẫn cùng một hình -> bỏ qua
      if (c.chart || c.screenshotFile) break;   // đã có hình khác -> dừng
      if (c.start >= until) break;              // quá lâu -> thôi, tránh hình chết
      c.chart = src.chart;
      c.screenshotFile = src.screenshotFile;
      c.screenshotUrl = src.screenshotUrl;
      c.visualAt = src.visualAt ?? src.start;
    }
  }
}

// ---- 5d. Gán MỖI CHƯƠNG một màn hình ----
// Video mẫu chia bài thành chương ("01 / 09") và mỗi chương có đúng một
// màn hình chiếm khung, đứng yên suốt chương, lời thoại chạy dưới đáy.
// Không chương nào được để trống -- đó chính là chỗ bản trước hỏng.
{
  const chapters = [];
  for (const c of cards) {
    const last = chapters[chapters.length - 1];
    if (!last || last.label !== c.section) {
      chapters.push({ label: c.section, cards: [c], start: c.start, end: c.out });
    } else {
      last.cards.push(c); last.end = c.out;
    }
  }
  let BRANDS = {};
  try { BRANDS = JSON.parse(fs.readFileSync('src/logos.json', 'utf8')); } catch { /* chưa có logo */ }

  // Ảnh trang nguồn THẬT do phía Python chụp trước (sourceshot.py), đã lọc
  // bỏ trang chặn bot / trang trắng. Không có file -> video vẫn dựng bình thường.
  let SHOTS = [];
  try { SHOTS = JSON.parse(fs.readFileSync('ref/shots.json', 'utf8')); } catch { /* không có ảnh nguồn */ }

  const timeline = buildTimeline(chapters, {
    brands: BRANDS,
    shots: SHOTS,
    duration: DURATION,
    elementOf: pickElementKind,
    listOf: cardsFromText,
    fallbackList: cardsFromText(CARDS.flat()
      .map((r) => (r.startsWith('~') ? r.slice(1) : r)).join(' ')),
    // chữ trên màn hình lấy từ KỊCH BẢN, không lấy chữ nhận diện được
    scriptLines: (si) => (CARDS[si] || []).map((r) => (r.startsWith('~') ? r.slice(1) : r)),
  });

  // Thẻ nhận màn hình đang có hiệu lực tại giây của nó -> màn chỉ xuất hiện
  // khi câu sinh ra nó ĐÃ được nói, và giữ nguyên cho tới màn kế tiếp.
  let ti = -1;
  for (const c of cards) {
    while (ti + 1 < timeline.length && timeline[ti + 1].at <= c.start + 0.01) ti++;
    if (ti >= 0) c.screen = timeline[ti].screen;
  }

  console.log(`màn hình: ${timeline.length} màn -> `
    + timeline.map((x) => `${x.screen.kind}@${x.at.toFixed(0)}s`).join(', '));
}

// Phụ đề = nguyên văn lời nói. Chỉ có khi nhận diện giọng nói dùng được --
// đoán theo khoảng lặng thì chữ sẽ không phải lời thật, thà không hiện.
const subtitle = usedRealWords
  ? realWords.map((r) => ({ text: r.w, start: r.start, end: r.end }))
  : [];

const out = {
  fps: FPS, duration: DURATION,
  durationInFrames: Math.ceil(DURATION * FPS) + 18,
  cards, subtitle,
};
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
