/**
 * Rút CÁC THẺ NHỎ từ những câu liệt kê trong lời nói.
 *
 * Bản mẫu dùng rất nhiều dạng này: một nhãn ngắn phía trên, rồi 2-4 hộp bo
 * góc, mỗi hộp là một mục ("Mã nguồn mở / Giấy phép MIT", "Có ngay trên
 * API / Tên gọi: deepseek-flash"). Trước đây ta không có dạng nào như vậy
 * nên những đoạn liệt kê -- vốn rất hợp để dựng thẻ -- lại rơi vào màn chữ
 * suông.
 *
 * Trong bản thu thật có sẵn những câu đúng kiểu đó:
 *
 *   "Astra tự sửa phần mềm, tự viết báo cáo và tự giám sát production."
 *   -> 3 thẻ: tự sửa phần mềm | tự viết báo cáo | tự giám sát production
 *
 * Nguyên tắc vẫn là KHÔNG BỊA: mỗi thẻ là một mệnh đề cắt nguyên văn ra,
 * không thêm chữ nào. Và chỉ nhận khi các mệnh đề THỰC SỰ song song nhau
 * (cùng từ mở đầu), nếu không thì một câu có dấu phẩy bất kỳ cũng bị xé
 * thành thẻ vô nghĩa.
 */

const MARKS = new RegExp('[̀-ͯ]', 'g');
const bare = (s) => String(s).toLowerCase().replace(/đ/g, 'd').normalize('NFD')
  .replace(MARKS, '').replace(/[^a-z0-9 ]/g, ' ').trim();

/** Tối thiểu/tối đa số thẻ hiện cùng lúc -- quá 4 là chữ bé không đọc nổi. */
const MIN_ITEMS = 2;
const MAX_ITEMS = 4;

function tidy(s) {
  return String(s).replace(/\s+/g, ' ').trim()
    .replace(/^[,;:.\s]+/, '').replace(/[,;:.\s]+$/, '');
}

/** Tách một câu thành các mệnh đề song song, hoặc null nếu không phải liệt kê. */
export function listItemsOf(sentence) {
  const text = tidy(sentence);
  if (!text) return null;

  // Tách ở dấu phẩy và liên từ "và" / "rồi" -- những chỗ người nói ngắt ý.
  const parts = text.split(/,|\svà\s|\srồi\s/i).map(tidy)
    .filter((p) => {
      const n = p.split(/\s+/).length;
      return n >= 2 && n <= 9;
    });
  if (parts.length < MIN_ITEMS) return null;

  // Song song = ít nhất hai mệnh đề mở đầu bằng cùng một từ ("tự", "có"...).
  const heads = parts.map((p) => bare(p).split(' ')[0]);
  const tally = new Map();
  for (const h of heads) tally.set(h, (tally.get(h) || 0) + 1);
  let topHead = '', topCount = 0;
  for (const [h, c] of tally) if (c > topCount) { topCount = c; topHead = h; }
  if (topCount < 2) return null;

  // Mệnh đề ĐẦU thường còn dính chủ ngữ: "Astra tự sửa phần mềm, tự viết
  // báo cáo và tự giám sát production" -- vế đầu mở bằng "Astra" nên bị loại
  // oan, mất luôn một thẻ có thật. Nếu vế đó CÓ CHỨA từ mở đầu chung thì cắt
  // bỏ phần chủ ngữ để nó về đúng dạng song song với các vế còn lại.
  const aligned = parts.map((p) => {
    const w = p.split(/\s+/);
    const b = w.map(bare);
    if (b[0] === topHead) return p;
    const at = b.indexOf(topHead);
    return at > 0 ? w.slice(at).join(' ') : p;
  });

  // Giữ đúng những mệnh đề cùng kiểu, bỏ vế lạc loài (thường là mệnh đề dẫn).
  const kept = aligned.filter((p) => bare(p).split(' ')[0] === topHead).slice(0, MAX_ITEMS);
  if (kept.length < MIN_ITEMS) return null;

  return kept.map((p) => ({ label: p.charAt(0).toUpperCase() + p.slice(1) }));
}

/** Quét toàn bộ lời nói của một chương, trả về bộ thẻ ĐẦU TIÊN tìm được. */
export function cardsFromText(text) {
  const sentences = String(text).split(/(?<=[.!?])\s+/);
  for (const s of sentences) {
    const items = listItemsOf(s);
    if (items) return items;
  }
  return null;
}
