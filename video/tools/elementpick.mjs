/**
 * Chọn HÌNH MINH HOẠ theo nội dung một chương.
 *
 * Bản trước dò từ khoá trên một dòng phụ đề ba từ, nên một chữ "giá" lạc ở
 * đâu đó kéo cái thẻ tiền hiện suốt cả những câu chẳng liên quan -- đo thật:
 * giọng đang nói "báo cáo, và tự giám sát" mà màn hình trưng thẻ "chi phí".
 * Ở đây dò trên TOÀN VĂN kịch bản của cả chương, và chỉ nhận khi từ khoá
 * xuất hiện đủ rõ; không khớp thì trả null để chương dùng dạng khác.
 */
const MARKS = new RegExp('[\u0300-\u036f]', 'g');
const bare = (s) => String(s).toLowerCase().replace(/đ/g, 'd').normalize('NFD')
  .replace(MARKS, '').replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ');

const RULES = [
  { kind: 'terminal', words: ['dong lenh', 'terminal', 'cli', 'cau lenh', 'go code', 'viet code', 'dong code'] },
  { kind: 'barrier',  words: ['gioi han', 'han ngach', 'chan', 'rao can', 'siet', 'han muc'] },
  { kind: 'checks',   words: ['kiem thu', 'kiem tra', 'giam sat', 'quy trinh', 'tu sua'] },
  { kind: 'warning',  words: ['rui ro', 'nguy hiem', 'su co', 'canh bao', 'that bai'] },
  { kind: 'human',    words: ['thu cong', 'nghiep du', 'thay the con nguoi', 'go thue'] },
  { kind: 'sandbox',  words: ['tu van hanh', 'tu dong', 'tu chay', 'production', 'he thong'] },
];

/** Số lần một chương phải nhắc tới chủ đề thì hình mới được coi là đúng. */
const MIN_HITS = 2;

export function pickElementKind(text) {
  const t = ' ' + bare(text) + ' ';
  let best = null, bestHits = 0;
  for (const r of RULES) {
    let hits = 0;
    for (const w of r.words) {
      let i = t.indexOf(' ' + w);
      while (i !== -1) { hits++; i = t.indexOf(' ' + w, i + 1); }
    }
    if (hits > bestHits) { bestHits = hits; best = r.kind; }
  }
  return bestHits >= MIN_HITS ? best : null;
}
