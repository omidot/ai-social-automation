/**
 * Dựng hình MINH HOẠ TỪ CHÍNH LỜI NÓI.
 *
 * Trước đây biểu đồ chỉ xuất hiện khi mô hình viết kịch bản chịu gắn thẻ
 * 'chart' -- đo thật: 1 biểu đồ trên 38 card, nên 95% thời lượng màn hình
 * trống trong khi giọng đọc đang đọc ra đầy số liệu. Ví dụ có thật trong
 * một bản thu:
 *
 *   "Gói Plus chỉ được từ 5 đến 45 tin. Gói Pro 100 đô được 25 đến 225
 *    tin. Gói Pro 200 đô nhận 100 đến 900 tin."
 *
 * Ba con số đó đáng lẽ phải thành một biểu đồ hiện ra đúng lúc nói, thay
 * vì một khung đen. Module này đọc bản ghi lời nói (có mốc thời gian
 * từng từ do Whisper trả về) và tự dựng biểu đồ, gắn đúng vào giây mà con
 * số được nói ra.
 *
 * Nguyên tắc: KHÔNG BỊA. Mọi nhãn và con số đều cắt thẳng từ lời nói.
 */

const MARKS = new RegExp('[̀-ͯ]', 'g');
const bare = (s) =>
  String(s).toLowerCase().replace(/đ/g, 'd').normalize('NFD').replace(MARKS, '')
    .replace(/[^a-z0-9]/g, '');

/** Từ báo hiệu phần chủ ngữ (nhãn) đã hết, phần số liệu bắt đầu. */
const TRIGGERS = new Set([
  'duoc', 'nhan', 'chi', 'co', 'la', 'len', 'tu', 'khoang', 'gom', 'dat',
  'mat', 'ton', 'giam', 'tang', 'con', 'toi', 'den', 'vao', 'sau', 'trong',
]);

/** Đơn vị đi sau con số -- dùng để nhận ra con số này có nghĩa gì. */
const UNITS = new Map([
  ['tin', 'tin'], ['phut', 'phút'], ['giay', 'giây'], ['gio', 'giờ'],
  ['ngay', 'ngày'], ['thang', 'tháng'], ['nam', 'năm'], ['lan', 'lần'],
  ['do', '$'], ['usd', '$'], ['dola', '$'], ['dong', 'đ'],
  ['phantram', '%'], ['diem', 'điểm'], ['ty', 'tỷ'], ['trieu', 'triệu'],
  ['nghin', 'nghìn'], ['token', 'token'], ['dong2', 'dòng'],
]);

const NUM = /^(\d+(?:[.,]\d+)?)([%x])?$/;

/** Đơn vị chỉ NGÀY THÁNG -- "ngày 3 tháng 9" không phải số liệu để vẽ cột. */
const DATE_UNITS = new Set(['ngay', 'thang', 'nam']);

/** Từ mở đầu câu điều kiện -- nhãn bắt đầu bằng mấy từ này là nhãn rác. */
const LEAD_NOISE = new Set(['neu', 'voi', 'va', 'nhung', 'ma', 'thi', 'khi', 'boi', 'vi', 'do']);

/**
 * Đọc một token thành số. PHẢI là token số nguyên chất (cho phép dấu câu
 * ở đuôi và hậu tố %/x) -- nếu bóc chữ ra khỏi token thì "GPT6" thành 6,
 * "GPT-5" thành 5, và cả tên model biến thành số liệu giả. Đo thật: lỗi
 * này sinh ra 3 biểu đồ rác trên một bản thu.
 */
function numOf(word) {
  const t = String(word).trim().replace(/^[("'-]+/, '').replace(/[,.;:!?)"']+$/, '');
  const m = NUM.exec(t);
  if (!m) return null;
  const v = Number(m[1].replace(/\./g, '').replace(',', '.'));
  if (!Number.isFinite(v)) return null;
  return { value: v, suffix: m[2] ?? '' };
}

/** Cắt chuỗi từ đã nói thành các câu (kết ở từ có dấu chấm/hỏi/than). */
export function sentencesOf(words) {
  const out = [];
  let cur = [];
  for (const w of words) {
    cur.push(w);
    if (/[.!?]\s*$/.test(w.w)) { out.push(cur); cur = []; }
  }
  if (cur.length) out.push(cur);
  return out.filter((s) => s.length > 0);
}

/**
 * Rút một "sự kiện số liệu" từ một câu: nhãn (chủ ngữ) + con số cuối cùng
 * + đơn vị. Trả về null nếu câu không có số đáng vẽ.
 */
export function factOf(sentence) {
  // Chỉ con số CÓ ĐƠN VỊ mới là số liệu. Không có đơn vị thì không biết
  // nó đo cái gì -- vẽ ra chỉ là con số trôi nổi vô nghĩa, và phần lớn
  // những con số như vậy hoá ra là mảnh tên model hoặc số phiên bản.
  const cands = [];
  sentence.forEach((w, i) => {
    const p = numOf(w.w);
    if (!p) return;
    let unit = p.suffix === '%' ? '%' : p.suffix === 'x' ? 'x' : '';
    let unitKey = '';
    if (!unit && i + 1 < sentence.length) {
      unitKey = bare(sentence[i + 1].w);
      const u = UNITS.get(unitKey);
      if (u) unit = u;
    }
    if (!unit) return;
    if (DATE_UNITS.has(unitKey)) return;            // "ngày 3 tháng 9"
    // "ngày 3", "tháng 9" -- từ đứng TRƯỚC cũng đủ tố cáo là mốc lịch
    if (i > 0 && DATE_UNITS.has(bare(sentence[i - 1].w))) return;
    cands.push({ i, value: p.value, unit });
  });
  if (cands.length === 0) return null;

  // Con số mang tải ý nghĩa thường nằm SAU CÙNG: "Gói Pro 100 đô được 25
  // đến 225 tin" -- 100 đô là mô tả gói, 225 tin mới là điều đang nói.
  const pick = cands[cands.length - 1];

  // nhãn = phần đầu câu tới từ bản lề đầu tiên (tối đa 4 từ), giữ nguyên
  // chữ đã nói -- "Gói Pro 100 đô", "Gói Plus"...
  let stop = sentence.findIndex((w) => TRIGGERS.has(bare(w.w)));
  if (stop <= 0) stop = Math.min(3, pick.i);
  stop = Math.min(stop, 4, pick.i);
  const words = sentence.slice(0, stop);
  if (words.length === 0) return null;
  if (LEAD_NOISE.has(bare(words[0].w))) return null;   // "Nếu bạn không biết..."
  const label = words.map((w) => w.w).join(' ').replace(/[,.;:]+$/, '').trim();
  if (!label) return null;

  return {
    label, value: pick.value, unit: pick.unit,
    start: sentence[0].start,
    at: sentence[pick.i].start,
    end: sentence[sentence.length - 1].end,
  };
}

/** Khoảng cách tối đa giữa hai câu để coi là cùng một mạch số liệu. */
const GROUP_GAP = 6.0;
/** Số hàng tối đa một biểu đồ -- quá nữa thì chữ bé không đọc nổi. */
const MAX_ROWS = 4;

/**
 * Quét cả bản ghi, gom các câu có số liệu liền kề cùng đơn vị thành một
 * biểu đồ. Trả về danh sách {kind, items, unit, start, end}.
 */
export function chartsFromSpeech(words) {
  const sents = sentencesOf(words);
  const facts = [];
  sents.forEach((s, si) => {
    const f = factOf(s);
    if (f) facts.push({ ...f, si });
  });

  /**
   * Nhãn cho cả bảng số liệu, lấy từ CÂU DẪN ngay trước nhóm -- ví dụ thật:
   * "Bảng hạn ngạch tin nhắn cục bộ trong mỗi năm giờ của các gói." rồi mới
   * tới ba con số. Câu đó nói bảng này đo cái gì, và nó là lời nói có thật
   * nên không có chuyện bịa. Chỉ nhận câu KHÔNG chứa số (câu có số là một
   * mốc dữ liệu khác, không phải lời dẫn) và đủ ngắn để in một dòng.
   */
  const introOf = (si) => {
    const prev = sents[si - 1];
    if (!prev || prev.length > 12) return '';
    if (prev.some((w) => numOf(w.w))) return '';
    const text = prev.map((w) => w.w).join(' ').replace(/[.,;:!?]+$/, '').trim();
    return text.length <= 52 ? text : '';
  };

  const charts = [];
  let i = 0;
  while (i < facts.length) {
    const group = [facts[i]];
    let j = i + 1;
    // Chỉ gộp các câu LIỀN KỀ NHAU. Một câu không số chen vào giữa gần như
    // luôn là câu đổi ngữ cảnh -- bản thu thật có "hạn ngạch mỗi năm giờ"
    // rồi "hạn mức hàng tuần còn siết chặt hơn"; gộp hai nhóm đó vào một
    // biểu đồ là dựng ra số liệu sai, dù mọi con số đều có thật.
    while (j < facts.length && group.length < MAX_ROWS
           && facts[j].unit === facts[i].unit
           && facts[j].si === group[group.length - 1].si + 1
           && facts[j].start - group[group.length - 1].end <= GROUP_GAP) {
      group.push(facts[j]); j++;
    }

    if (group.length >= 2) {
      // Nhiều mốc cùng đơn vị -> so kè trực tiếp bằng thanh ngang.
      charts.push({
        kind: 'hbar',
        items: group.map((g) => ({ label: g.label, value: g.value })),
        unit: group[0].unit,
        title: introOf(group[0].si),
        start: group[0].at,
        end: group[group.length - 1].end,
      });
      i = j;
    } else {
      // Một con số đứng lẻ -> khối số liệu, vẫn hơn khung trống.
      charts.push({
        kind: 'stat',
        items: [{ label: group[0].label, value: group[0].value }],
        unit: group[0].unit,
        title: introOf(group[0].si),
        start: group[0].at,
        end: group[0].end,
      });
      i += 1;
    }
  }
  return charts;
}
