// DỰ ÁN: ADS-BOT SHORT (40s) — cấu hình Gemini cũ nằm ở tools/gemini-backup/
// Thứ tự chữ phải khớp lời đọc trong voice-adsbot.mp3 — đó là cách timeline tự căn giờ.
// Tiền tố "~" = CHỈ GIỮ CHỖ TÍNH GIỜ, không hiện lên màn hình (chủ yếu là chữ đệm "cái").
// "Cloud Code" trong bản ghi gốc đã sửa thành "Claude Code" theo xác nhận của người dùng.
// Đệm ẩn được đặt ở CUỐI card "Claude Code" và card "bạn đang ngủ," để hai dòng
// quan trọng nhất (chỗ chèn ảnh + chỗ mở twist) có đủ thời gian hiển thị.
export const CARDS = [
  ["Với", "~cái", "sự phát triển không ngừng của AI ngày nay,"],
  ["sẽ là một", "~cái", "việc rất là khó khăn"],
  ["cho một người bình thường muốn làm kinh doanh."],
  ["Bây giờ muốn suy nghĩ,", "AI nó cũng có thể", "suy nghĩ cho các bạn."],
  ["Làm sao để thực hiện", "~cái", "ý tưởng kinh doanh,"],
  ["AI nó cũng có thể", "thực hiện cho các bạn."],
  ["Và sau khi thực hiện", "ý tưởng kinh doanh đó,"],
  ["bạn có thể vào", "Claude Code", "~schedule những"],
  ["~cái", "đó để mà chạy ads."],
  ["Và trong khi", "bạn đang ngủ,", "~có"],
  ["hàng ngàn,", "hàng ngàn,", "hàng chục ngàn", "robot ở bên China"],
  ["tung ra hàng triệu", "~cái", "video quảng cáo", "sản phẩm đó."],
  ["Bạn không thể nào", "bạn đăng từng", "~cái", "video mà bạn cạnh tranh nổi"],
  ["với những", "~cái", "con robot đó."],
  ["Những", "~cái", "con robot đó", "nó được tạo ra", "~bởi"],
  ["những", "~cái", "công ty lớn hơn bạn"],
];

// Chip chương trên đầu video — [cardIndexBắtĐầu, nhãn]
export const SECTIONS = [
  [0,  "AI THAY BẠN NGHĨ"],
  [7,  "CLAUDE CODE SCHEDULE ADS"],
  [9,  "TRONG KHI BẠN NGỦ"],
  [14, "SỰ THẬT"],
];
