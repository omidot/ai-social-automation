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
      // Bộ thẻ chỉ bật lên ĐÚNG LÚC người đọc bắt đầu câu liệt kê đó,
      // không phải từ đầu chương.
      const cardsAt = findSpokenTime(cards, listed[0].label);
      out.set(ci, { kind: 'cards', items: listed, eyebrow: ch.label || '',
                    at: cardsAt ?? at });
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
      const own = listOf(chText.join(' '));
      // Hình bật lên đúng lúc chủ đề của nó được nói tới.
      const elAt = findSpokenTime(cards, (own && own[0] && own[0].label) || el);
      out.set(ci, { kind: 'element', element: el, eyebrow: ch.label || '',
                    // Chương này không có câu liệt kê riêng -> mượn câu liệt kê
                    // THẬT của bài, vẫn là lời người đọc nói ra, không bịa chữ.
                    items: own || fallbackList || [], at: elAt ?? at });
      return;
    }

    // 4. Còn lại -> câu chốt của chương, lấy nguyên văn từ kịch bản.
    const sentence = chText.join(' ').trim();
    const sp = splitStatement(sentence);
    if (sp) {
      const stAt = findSpokenTime(cards, sp.lead) ?? findSpokenTime(cards, sp.highlight);
      out.set(ci, {
        kind: 'statement', at: stAt ?? at,
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

/**
 * Tìm GIÂY mà một cụm từ được nói ra, trong phạm vi các thẻ của một chương.
 *
 * Đây là thứ quyết định "nói tới đâu hiện tới đó". Trước đây mọi màn hình
 * đều bật ngay đầu chương, nên bộ thẻ liệt kê hiện lên từ giây đầu trong
 * khi mãi mười giây sau người đọc mới nói câu đó -- hình chạy trước lời.
 *
 * So khớp theo chuỗi từ đã bỏ dấu, cho phép hụt một vài từ (người đọc
 * không bao giờ đọc y hệt kịch bản). Trả về null nếu không tìm thấy, để
 * bên gọi tự quyết định lấy mốc nào.
 */
export function findSpokenTime(cards, phrase) {
  const MK = new RegExp('[̀-ͯ]', 'g');
  const nm = (s) => String(s).toLowerCase().replace(/đ/g, 'd').normalize('NFD')
    .replace(MK, '').replace(/[^a-z0-9]/g, '');

  const want = String(phrase).split(/\s+/).map(nm).filter((w) => w.length > 1);
  if (want.length === 0) return null;

  const flat = [];
  for (const c of cards) {
    for (const l of c.lines || []) {
      for (const w of l.words || []) flat.push({ n: nm(w.text), t: w.start });
    }
  }
  if (flat.length === 0) return null;

  // Khớp phải LIỀN MẠCH. Bản đầu cho phép nhảy tuỳ ý giữa các từ, nên cụm
  // "tự sửa phần mềm" khớp được ngay từ từ số 0 bằng cách nhặt "tự" ở đầu
  // bài rồi "sửa" ở tận đâu đó -- mọi màn hình đều trả về giây 0.46. Giờ
  // giữa hai từ khớp chỉ được phép cách tối đa SKIP từ, và cả cụm phải nằm
  // gọn trong một quãng ngắn.
  const SKIP = 3;
  const need = Math.max(1, Math.ceil(want.length * 0.6));
  const maxSpan = want.length * 3 + 4;

  let best = null, bestHits = 0;
  for (let i = 0; i < flat.length; i++) {
    if (flat[i].n !== want[0]) continue;      // phải bắt đầu đúng từ đầu cụm
    let hits = 1, j = i + 1, wi = 1;
    while (wi < want.length && j < flat.length && j - i <= maxSpan) {
      let k = j, found = -1;
      while (k < flat.length && k - j <= SKIP) {
        if (flat[k].n === want[wi]) { found = k; break; }
        k++;
      }
      if (found < 0) { wi++; continue; }       // hụt một từ -> bỏ qua từ đó
      hits++; j = found + 1; wi++;
    }
    if (hits > bestHits) { bestHits = hits; best = flat[i].t; }
    if (hits === want.length) return flat[i].t;
  }
  return bestHits >= need ? best : null;
}

/**
 * Dựng DÒNG THỜI GIAN MÀN HÌNH theo MỐC NỘI DUNG, không theo khung chương.
 *
 * Cách cũ gán mỗi chương một màn rồi bật từ đầu chương. Hậu quả đo được:
 * bộ thẻ liệt kê bật ở giây 12.2 trong khi người đọc nói câu đó ở giây 7 --
 * hình chạy trước lời, đúng điều người dùng phàn nàn. Kể cả khi đã neo giờ,
 * việc kẹp `at` vào trong khung chương vẫn kéo nó lệch trở lại.
 *
 * Ở đây mỗi thứ đáng hiện đều tự khai GIỜ NÓ ĐƯỢC NÓI RA, tất cả đổ chung
 * một dòng thời gian rồi sắp theo giờ. Ảnh trang nguồn được chèn vào những
 * quãng trống dài, vì nó không gắn với một câu cụ thể nào.
 */
export function buildTimeline(chapters, opts) {
  const { brands = {}, scriptLines = () => [], shots = [], elementOf = () => null,
          listOf = () => null, fallbackList = null, duration = 0 } = opts || {};
  const MK = new RegExp('[̀-ͯ]', 'g');
  const norm = (s) => String(s).toLowerCase().replace(/đ/g, 'd').normalize('NFD')
    .replace(MK, '').replace(/[^a-z0-9]/g, '');

  const out = [];

  chapters.forEach((ch, ci) => {
    const cards = ch.cards;
    const srcs = [];
    for (const c of cards) if (c.src !== undefined && !srcs.includes(c.src)) srcs.push(c.src);
    const chText = srcs.flatMap((si) => scriptLines(si));

    // Mở bài: màn hook, luôn ở ngay đầu chương đầu.
    if (ci === 0) {
      const spokenW = cards.flatMap((c) => c.lines.flatMap((l) => (l.words ?? []).map((w) => w.text)));
      const found = [];
      for (const w of spokenW) {
        const b = brands[norm(w)];
        if (b && !found.some((x) => x.label === b.label)) found.push(b);
      }
      out.push({ at: ch.start, screen: {
        kind: 'hook', at: ch.start, eyebrow: ch.label || '',
        title: (chText[0] || ch.label || '').trim(),
        subtitle: (chText[1] || '').trim(),
        tiles: found.slice(0, 3).map((b, i) => ({
          label: b.label, file: b.file,
          verdict: found.length >= 2 ? (i === 0 ? 'win' : 'lose') : undefined,
        })),
      } });
    }

    // Bảng số: bật đúng giây con số đầu tiên của nó được đọc.
    const seenChart = new Set();
    for (const c of cards) {
      if (!c.chart || !c.chart.items || !c.chart.items.length) continue;
      const key = JSON.stringify(c.chart.items);
      if (seenChart.has(key)) continue;
      seenChart.add(key);
      const at = c.visualAt ?? c.start;
      const titled = c.chart.title ? c.chart : { ...c.chart, title: ch.label || '' };
      // Số phải hãm lại đúng lúc người đọc nói xong con số đó.
      const chart = timeChartItems(cards, titled, at);
      out.push({ at, screen: { kind: 'panel', chart, at } });
    }

    // Bộ thẻ: bật đúng lúc bắt đầu câu liệt kê.
    const listed = listOf(chText.join(' '));
    if (listed) {
      const at = findSpokenTime(cards, listed[0].label);
      if (at !== null) {
        out.push({ at, screen: { kind: 'cards', items: listed, eyebrow: ch.label || '', at } });
      }
    }

    // Hình vẽ: bật đúng lúc chủ đề của nó được nhắc.
    const el = elementOf(chText.join(' '));
    if (el) {
      const anchor = (listed && listed[0] && listed[0].label) || el;
      const at = findSpokenTime(cards, anchor);
      if (at !== null) {
        out.push({ at, screen: { kind: 'element', element: el, eyebrow: ch.label || '',
                                 items: listed || fallbackList || [], at } });
      }
    }

    // Câu chốt: bật đúng lúc bắt đầu câu đó.
    const sp = splitStatement(chText.join(' '));
    if (sp) {
      const at = findSpokenTime(cards, sp.lead);
      if (at !== null) {
        out.push({ at, screen: { kind: 'statement', at, eyebrow: ch.label || '',
                                 lead: sp.lead, highlight: sp.highlight } });
      }
    }
  });

  out.sort((a, b) => a.at - b.at);

  // Hai màn sát nhau quá thì chớp nhoáng, người xem chưa kịp nhìn.
  const MIN_GAP = 5;
  const kept = [];
  for (const x of out) {
    if (kept.length && x.at - kept[kept.length - 1].at < MIN_GAP) continue;
    kept.push(x);
  }

  // Ảnh trang nguồn không gắn với câu nào -> chèn vào quãng TRỐNG DÀI nhất,
  // nơi màn hình đứng yên lâu nhất và cần đổi hình.
  const GAP_FOR_SHOT = 16;
  for (const sh of shots) {
    let bi = -1, best = GAP_FOR_SHOT;
    for (let i = 0; i < kept.length; i++) {
      const end = i + 1 < kept.length ? kept[i + 1].at : duration;
      const gap = end - kept[i].at;
      if (gap > best) { best = gap; bi = i; }
    }
    if (bi < 0) break;
    const end = bi + 1 < kept.length ? kept[bi + 1].at : duration;
    const at = kept[bi].at + (end - kept[bi].at) / 2;
    kept.splice(bi + 1, 0, { at, screen: {
      kind: 'shot', file: sh.file, sourceUrl: sh.url,
      eyebrow: kept[bi].screen.eyebrow || '', at } });
  }

  if (kept.length) kept[0].at = 0;
  return kept;
}

/**
 * Gắn GIỜ ĐỌC THẬT cho từng con số trong một biểu đồ.
 *
 * Biểu đồ do kịch bản gắn tay chỉ có giá trị, không có mốc thời gian, nên
 * số trên màn chạy theo nhịp rải đều -- lệch hẳn với lúc người đọc thật sự
 * đọc con số đó. Ở đây dò chính con số trong bản ghi lời nói và lấy mốc gần
 * nhất sau khi bảng bật lên, để số hãm lại đúng lúc nói xong.
 */
export function timeChartItems(cards, chart, fromTime) {
  if (!chart || !Array.isArray(chart.items)) return chart;
  const flat = [];
  for (const c of cards) {
    for (const l of c.lines || []) {
      for (const w of l.words || []) {
        const t = String(w.text).replace(/^[("'-]+/, '').replace(/[,.;:!?)"']+$/, '');
        if (/^\d+([.,]\d+)?$/.test(t)) {
          flat.push({ v: Number(t.replace(/\./g, '').replace(',', '.')),
                      a: w.start, e: w.end });
        }
      }
    }
  }
  if (!flat.length) return chart;

  let cursor = fromTime ?? 0;
  const items = chart.items.map((it) => {
    if (typeof it.at === 'number') { cursor = Math.max(cursor, it.at); return it; }
    // con số đúng bằng giá trị, xuất hiện sớm nhất kể từ con trỏ hiện tại
    const hit = flat.find((f) => f.v === it.value && f.a >= cursor - 0.5);
    if (!hit) return it;
    cursor = hit.e;
    return { ...it, at: hit.a, numEnd: hit.e };
  });
  return { ...chart, items };
}
