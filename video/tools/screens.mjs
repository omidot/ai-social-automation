/**
 * GÁN MỖI CHƯƠNG MỘT MÀN HÌNH.
 *
 * Đây là điều bản dựng trước làm sai từ gốc. Video mẫu chia bài thành các
 * chương ("01 / 09"), và MỖI CHƯƠNG có đúng một màn hình chiếm khung đứng
 * yên suốt chương đó, còn lời thoại chạy thành dòng nhỏ dưới đáy. Bản
 * trước lại lấy nền đen + chữ chạy làm mặc định rồi thỉnh thoảng mới chèn
 * một biểu đồ, nên phần lớn thời lượng màn hình trống.
 *
 * Ở đây không chương nào được để trống: mỗi chương luôn nhận một trong
 * bốn dạng — hook / panel / shot / statement — theo thứ tự ưu tiên dựa
 * trên dữ liệu THẬT có được cho chương đó.
 *
 * Mọi chữ dùng trên màn hình đều lấy từ KỊCH BẢN (đúng chính tả) hoặc từ
 * số liệu đã rút từ lời nói. Không bịa thêm chữ nào.
 */

/** Cắt một câu dài thành (phần dẫn, phần nhấn) để dựng màn "statement". */
export function splitStatement(text) {
  const clean = String(text).replace(/\s+/g, ' ').trim().replace(/[.]+$/, '');
  const words = clean.split(' ');
  if (words.length < 4) return null;
  // Phần nhấn = vế sau dấu phẩy cuối, nếu có; nếu không thì ~40% cuối câu.
  const ci = clean.lastIndexOf(', ');
  if (ci > 10 && clean.length - ci > 12 && clean.length - ci < 46) {
    return { lead: clean.slice(0, ci + 1), highlight: clean.slice(ci + 2) };
  }
  const cut = Math.max(2, Math.ceil(words.length * 0.6));
  const lead = words.slice(0, cut).join(' ');
  const highlight = words.slice(cut).join(' ');
  if (!highlight || highlight.length > 44) return null;
  return { lead, highlight };
}

/**
 * @param chapters [{label, cards:[card], start, end}]
 * @param opts {brands: Record<key,{label,file}>, scriptLines: (srcIndex)=>string[]}
 * @returns Map<chapterIndex, screen>
 */
export function assignScreens(chapters, opts) {
  const { brands = {}, scriptLines = () => [], shots = [], elementOf = () => null,
          listOf = () => null, fallbackList = null } = opts || {};
  // Ảnh nguồn thật được rải đều, mỗi ảnh dùng đúng một lần -- ảnh lặp lại
  // ở hai chương khác nhau làm người xem tưởng đang xem lại đoạn cũ.
  let shotAt = 0;
  const MARKS = new RegExp('[̀-ͯ]', 'g');
  const norm = (s) => String(s).toLowerCase().replace(/đ/g, 'd').normalize('NFD')
    .replace(MARKS, '').replace(/[^a-z0-9]/g, '');

  const out = new Map();

  // Chương quá dài mà giữ nguyên một màn thì người xem đứng hình cả nửa
  // phút. Bản mẫu đổi màn khoảng 16 giây một lần (9 màn / 2 phút 24).
  // Chương dài hơn ngưỡng này được tách đôi: nửa đầu giữ màn chính, nửa sau
  // nhận màn kế tiếp trong thứ tự ưu tiên.
  const SPLIT_AFTER = 20;

  chapters.forEach((ch, ci) => {
    const cards = ch.cards;
    const at = ch.start;

    // Toàn văn kịch bản của chương -- dùng chung cho mọi nhánh bên dưới.
    const srcs = [];
    for (const c of cards) if (c.src !== undefined && !srcs.includes(c.src)) srcs.push(c.src);
    const chText = srcs.flatMap((si) => scriptLines(si));

    // 0. Chương MỞ ĐẦU luôn là màn HOOK. Mở bài mà đã đâm thẳng vào bảng
    // biểu hay bộ thẻ thì mất hẳn cú móc đầu video.
    if (ci === 0) {
      const spokenW = cards.flatMap((c) => c.lines.flatMap((l) => (l.words ?? []).map((w) => w.text)));
      const found = [];
      for (const w of spokenW) {
        const b = brands[norm(w)];
        if (b && !found.some((x) => x.label === b.label)) found.push(b);
      }
      out.set(ci, {
        kind: 'hook', at,
        eyebrow: ch.label || '',
        title: (chText[0] || ch.label || '').trim(),
        subtitle: (chText[1] || '').trim(),
        tiles: found.slice(0, 3).map((b, i) => ({
          label: b.label, file: b.file,
          verdict: found.length >= 2 ? (i === 0 ? 'win' : 'lose') : undefined,
        })),
      });
      return;
    }

    // 1. Ảnh chụp thật luôn thắng: nó là bằng chứng, không phải minh hoạ.
    const shot = cards.find((c) => c.screenshotFile);
    if (shot) {
      out.set(ci, { kind: 'shot', file: shot.screenshotFile,
                    sourceUrl: shot.screenshotUrl, eyebrow: ch.label || '', at });
      return;
    }

    // 2. Có số liệu -> tấm bảng số. Đây là dạng chiếm phần lớn bản mẫu.
    const withChart = cards.find((c) => c.chart && c.chart.items && c.chart.items.length);
    if (withChart) {
      // Bảng số luôn phải có nhãn nói nó đo cái gì; thiếu thì mượn nhãn chương.
      const chart = withChart.chart.title
        ? withChart.chart
        : { ...withChart.chart, title: ch.label || '' };
      out.set(ci, { kind: 'panel', chart, at: withChart.visualAt ?? at });
      return;
    }

    // Toàn văn kịch bản của CẢ chương. Trước đây chỉ lấy dòng của thẻ đầu
    // chương, nên câu liệt kê nằm ở thẻ thứ ba không bao giờ được thấy.
    // 2a. Câu LIỆT KÊ -> bộ thẻ nhỏ. Bản mẫu dùng dạng này rất nhiều, và
    // một đoạn liệt kê ("tự sửa phần mềm, tự viết báo cáo, tự giám sát")
    // hợp với thẻ hơn hẳn so với dán một ảnh trang web lên.
    const listed = listOf(chText.join(' '));
    if (listed) {
      out.set(ci, { kind: 'cards', items: listed, eyebrow: ch.label || '', at });
      return;
    }

    // 2b. Không có số liệu -> ưu tiên ẢNH TRANG NGUỒN THẬT. Đây là thứ
    // bản mẫu dùng liên tục và cũng là bằng chứng cho điều đang nói.
    // Chương đầu thì không: mở bài phải là màn hook.
    if (ci > 0 && shotAt < shots.length) {
      const sh = shots[shotAt++];
      // Tiêu đề cho màn ảnh: nhãn chương, để người xem biết đang xem gì --
      // ảnh trang web đứng trần không có chú thích thì rất khó bám mạch.
      out.set(ci, { kind: 'shot', file: sh.file, sourceUrl: sh.url,
                    eyebrow: ch.label || '', at });
      return;
    }

    // 3b. Hết ảnh -> hình minh hoạ vẽ theo nội dung chương (terminal, hộp
    // tự vận hành, tường chặn...). Dò trên TOÀN VĂN chương, không phải một
    // dòng caption ba từ -- ba từ thì hiếm khi đủ biết đang kể chuyện gì.
    const el = elementOf(chText.join(' '));
    if (el) {
      // Chú thích cho các chấm quanh lõi, lấy từ câu liệt kê có thật.
      out.set(ci, { kind: 'element', element: el, eyebrow: ch.label || '',
                    // Chương này không có câu liệt kê riêng -> mượn câu liệt kê
                    // THẬT của bài, vẫn là lời người đọc nói ra, không bịa chữ.
                    items: listOf(chText.join(' ')) || fallbackList || [], at });
      return;
    }

    // 4. Còn lại -> câu chốt của chương, lấy nguyên văn từ kịch bản.
    const sentence = chText.join(' ').trim();
    const sp = splitStatement(sentence);
    if (sp) {
      out.set(ci, {
        kind: 'statement', at,
        eyebrow: ch.label || '',
        lead: sp.lead, highlight: sp.highlight,
      });
      return;
    }

    // 5. Không tách được câu -> vẫn phải có hình: dùng hook rút gọn.
    out.set(ci, {
      kind: 'hook', at,
      eyebrow: ch.label || '',
      title: (chText[0] || ch.label || '').trim(),
      subtitle: (chText[1] || '').trim(),
      tiles: [],
    });
  });

  return out;
}

/**
 * Màn PHỤ cho nửa sau của một chương quá dài. Dùng nguồn dữ liệu còn lại
 * chưa được màn chính tiêu thụ, nên không lặp lại y hệt nửa đầu.
 */
export function secondaryScreen(ch, primary, opts) {
  const { shots = [], listOf = () => null, scriptLines = () => [] } = opts || {};
  const srcs = [];
  for (const c of ch.cards) if (c.src !== undefined && !srcs.includes(c.src)) srcs.push(c.src);
  const text = srcs.flatMap((si) => scriptLines(si)).join(' ');
  const mid = ch.cards[Math.floor(ch.cards.length / 2)];
  const at = mid ? mid.start : ch.start;

  const listed = listOf(text);
  if (listed && primary.kind !== 'cards') {
    return { kind: 'cards', items: listed, eyebrow: ch.label || '', at };
  }
  const spare = shots.find((s) => s.file !== primary.file);
  if (spare && primary.kind !== 'shot') {
    return { kind: 'shot', file: spare.file, sourceUrl: spare.url,
             eyebrow: ch.label || '', at };
  }
  const sp = splitStatement(text);
  if (sp && primary.kind !== 'statement') {
    return { kind: 'statement', at, eyebrow: ch.label || '',
             lead: sp.lead, highlight: sp.highlight };
  }
  return null;
}
