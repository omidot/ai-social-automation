// DỰ ÁN: GEMINI SHORT — 33 card, khớp 1-1 với CARDS
// [variant, anchor, num, motionVào, motionRa]
// variant  : stack | hero | invert | mark | right | stair | numeral | strike
// motionVào: rise | fall | slideL | slideR | pop | slam   (wipe/spread/whoosh-đảo đã bỏ theo yêu cầu)
// motionRa : up | down | shrink | dissolve | wipeOut
export const LAYOUT = [
  ['stack',   'mid', null, 'rise',   'up'],        //  0 hook — bạn đang trả tiền
  ['hero',    'mid', null, 'pop',    'dissolve'],  //  1 chưa dùng tới bốn thứ này
  ['stack',   'low', null, 'fall',   'down'],      //  2 xem đến cuối / chạy khi bạn ngủ
  ['numeral', 'mid', 1,    'pop',    'up'],        //  3 ── mẹo 1
  ['stack',   'top', null, 'slideL', 'shrink'],    //  4 Personal Intelligence
  ['mark',    'mid', null, 'rise',   'wipeOut'],   //  5 ★ câu lệnh: đừng gật đầu với tôi
  ['stack',   'mid', null, 'fall',   'up'],        //  6 AI có xu hướng đồng ý
  ['hero',    'mid', null, 'slam',   'dissolve'],  //  7 không giúp bạn nghĩ tốt hơn
  ['right',   'low', null, 'slideR', 'down'],      //  8 15 giây, dùng được mãi
  ['numeral', 'mid', 2,    'pop',    'up'],        //  9 ── mẹo 2
  ['stair',   'mid', null, 'slideL', 'shrink'],    // 10 năm tab so sánh
  ['stair',   'mid', null, 'fall',   'down'],      // 11 gõ a còng, chọn cả năm tab
  ['mark',    'mid', null, 'rise',   'up'],        // 12 ★ nói cái nào hợp
  ['right',   'top', null, 'slideR', 'dissolve'],  // 13 nhảy tab 3-4 chục lần
  ['numeral', 'mid', 3,    'pop',    'up'],        // 14 ── mẹo 3
  ['stack',   'mid', null, 'slideL', 'shrink'],    // 15 nghiên cứu một chủ đề
  ['mark',    'mid', null, 'fall',   'down'],      // 16 ★ bắt nó hỏi ngược lại
  ['stair',   'mid', null, 'slideL', 'up'],        // 17 notebook → Audio Overview
  ['mark',    'mid', null, 'rise',   'wipeOut'],   // 18 ★ podcast từ nghiên cứu của bạn
  ['right',   'low', null, 'slideR', 'dissolve'],  // 19 nghe lúc chạy bộ
  ['numeral', 'mid', 4,    'pop',    'up'],        // 20 ── mẹo 4
  ['stack',   'mid', null, 'slideL', 'shrink'],    // 21 nối lịch và email
  ['stack',   'top', null, 'fall',   'down'],      // 22 đêm nó đọc hết thư
  ['mark',    'mid', null, 'rise',   'up'],        // 23 ★ tóm tắt trong Google Docs
  ['right',   'mid', null, 'slideR', 'shrink'],    // 24 dọn thư mục lộn xộn
  ['invert',  'mid', null, 'slam',   'wipeOut'],   // 25 ⚠ CẢNH BÁO giấy tờ cá nhân
  ['hero',    'mid', null, 'pop',    'dissolve'],  // 26 nghe hay đúng không
  ['invert',  'mid', null, 'fall',   'wipeOut'],   // 27 ★★ ổn mọi mặt, không xuất sắc
  ['mark',    'mid', null, 'rise',   'up'],        // 28 ★ rộng ≠ sâu
  ['stack',   'low', null, 'slideL', 'shrink'],    // 29 phần dễ nhất
  ['stair',   'mid', null, 'fall',   'down'],      // 30 Gems, Skills, Canvas
  ['stack',   'top', null, 'slideL', 'up'],        // 31 nằm trong bản đầy đủ
  ['mark',    'mid', null, 'rise',   'up'],        // 32 ★ CTA bấm xem
];
