// [variant, anchor, num, motionVào, motionRa] — 47 card, khớp 1-1 với CARDS
// variant  : stack | hero | invert | mark | right | stair | numeral | strike
// anchor   : top | mid | low
// motionVào: rise | fall | slideL | slideR | pop | slam | wipe | spread
// motionRa : up | down | shrink | dissolve | wipeOut
// Quy tắc: hai card liền nhau KHÔNG dùng chung motionVào.
export const LAYOUT = [
  ['stack',   'mid', null, 'rise',   'up'],        //  0 hook
  ['mark',    'top', null, 'fall',   'down'],      //  1 không phải viết code hộ
  ['stair',   'mid', null, 'slideL', 'shrink'],    //  2 giây cuối cùng
  ['hero',    'mid', null, 'pop',    'dissolve'],  //  3 sáu thứ / hai phút
  ['mark',    'mid', null, 'wipe',   'shrink'],    //  4 xem hết.
  ['right',   'low', null, 'slideR', 'up'],        //  5 bạn được trả tiền
  ['numeral', 'mid', 1,    'fall',   'dissolve'],  //  6 ── tính năng 1
  ['stair',   'mid', null, 'slideL', 'down'],      //  7 tự click, tự gõ phím
  ['stack',   'top', null, 'spread', 'shrink'],    //  8 đúng cái máy bạn đang ngồi
  ['stack',   'mid', null, 'slam',   'dissolve'],  //  9 không chiếm màn hình
  ['right',   'mid', null, 'slideR', 'up'],        // 10 ba con AI làm ba việc
  ['mark',    'mid', null, 'wipe',   'wipeOut'],   // 11 ★ nó không ngủ
  ['numeral', 'mid', 2,    'pop',    'up'],        // 12 ── tính năng 2
  ['strike',  'mid', null, 'fall',   'down'],      // 13 không phải gợi ý code
  ['stack',   'low', null, 'rise',   'shrink'],    // 14 hiện thẳng trên màn hình
  ['right',   'top', null, 'slideR', 'dissolve'],  // 15 một tuần + freelancer
  ['mark',    'mid', null, 'wipe',   'up'],        // 16 ★ một prompt.
  ['numeral', 'mid', 3,    'fall',   'shrink'],    // 17 ── tính năng 3
  ['strike',  'low', null, 'slam',   'up'],        // 18 không thuê ai
  ['mark',    'mid', null, 'wipe',   'dissolve'],  // 19 designer ngồi thẳng lưng
  ['numeral', 'mid', 4,    'pop',    'up'],        // 20 ── tính năng 4
  ['stair',   'mid', null, 'slideL', 'down'],      // 21 nhớ thói quen làm việc
  ['right',   'top', null, 'slideR', 'shrink'],    // 22 từ đầu mỗi sáng nữa
  ['hero',    'mid', null, 'slam',   'dissolve'],  // 23 đúng một giây.
  ['invert',  'mid', null, 'spread', 'wipeOut'],   // 24 ★ nghĩa là gì?
  ['stack',   'mid', null, 'rise',   'up'],        // 25 một bản sao
  ['stair',   'low', null, 'slideL', 'down'],      // 26 không nằm trong máy bạn
  ['mark',    'mid', null, 'wipe',   'shrink'],    // 27 ★ nhưng không miễn phí
  ['numeral', 'mid', 5,    'fall',   'up'],        // 28 ── tính năng 5
  ['stack',   'top', null, 'spread', 'dissolve'],  // 29 kéo dài nhiều tuần
  ['stair',   'mid', null, 'slideL', 'shrink'],    // 30 tự báo cáo lại
  ['numeral', 'mid', 6,    'pop',    'up'],        // 31 ── tính năng 6
  ['stair',   'mid', null, 'slideL', 'down'],      // 32 Gmail, Notion.
  ['right',   'low', null, 'slideR', 'dissolve'],  // 33 quan trọng nhất
  ['hero',    'mid', null, 'pop',    'shrink'],    // 34 câu vừa rồi,
  ['mark',    'mid', null, 'wipe',   'up'],        // 35 ★ và có Gmail của bạn
  ['hero',    'mid', null, 'slam',   'dissolve'],  // 36 đúng không?
  ['invert',  'mid', null, 'spread', 'wipeOut'],   // 37 ★★ Computer Use
  ['invert',  'mid', null, 'fall',   'wipeOut'],   // 38 ★★ năm 2024.
  ['mark',    'mid', null, 'wipe',   'up'],        // 39 ★ không phải dẫn đầu
  ['stack',   'top', null, 'rise',   'shrink'],    // 40 đua nhau nhét AI
  ['right',   'mid', null, 'slideR', 'down'],      // 41 cũng không phải Anthropic
  ['invert',  'mid', null, 'pop',    'wipeOut'],   // 42 ★★ học dùng nó trước
  ['stack',   'low', null, 'spread', 'dissolve'],  // 43 Codex mạnh cỡ nào
  ['stack',   'mid', null, 'rise',   'up'],        // 44 ★ Codex hay Claude Code?
  ['right',   'top', null, 'slideR', 'shrink'],    // 45 tôi đọc hết
  ['mark',    'mid', null, 'wipe',   'up'],        // 46 follow ủng hộ
];
