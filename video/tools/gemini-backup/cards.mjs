// DỰ ÁN: GEMINI SHORT (98s) — cấu hình Codex cũ nằm ở tools/codex-backup/
// Thứ tự chữ phải khớp lời đọc trong voice-gemini.mp3 — đó là cách timeline tự căn giờ.
// Tiền tố "~" = CHỈ GIỮ CHỖ TÍNH GIỜ, không hiện lên màn hình.
// Dòng ngắn được gộp lại cho ít dòng mà dày chữ hơn, và card cố gắng kết bằng dòng ẩn.
export const CARDS = [
  ["Bạn đang trả tiền cho Gemini", "mỗi tháng", "~và gần như chắc chắn"],
  ["chưa dùng tới bốn thứ này.", "~Ok, và đây là bốn mẹo."],
  ["Nhớ xem đến cuối video", "và nó sẽ chạy trong lúc bạn ngủ."],
  ["Mẹo thứ nhất là", "dạy AI cãi lại.", "~Trong phần Settings"],
  ["chọn phần Personal Intelligence.", "~Phần Instructions", "~gõ đúng một câu:"],
  ["Đừng gật đầu với tôi,", "ý nào yếu thì nói thẳng là yếu."],
  ["Mặc định AI có xu hướng đồng ý với bạn.", "~Một công cụ chỉ biết đồng ý"],
  ["thì không giúp bạn nghĩ tốt hơn."],
  ["Mười lăm giây để gõ. Dùng được mãi."],
  ["Mẹo thứ hai là", "hỏi năm tab cùng lúc.", "~Trong Chrome có nút Ask Gemini."],
  ["Đang mở năm tab", "so sánh khách sạn hay sản phẩm."],
  ["Gõ dấu a còng,", "chọn cả năm tab, hỏi một lần."],
  ["Nó đọc hết rồi nói cái nào hợp."],
  ["Một ngày bạn nhảy tab", "ba bốn chục lần,", "~cộng lại không nhỏ đâu."],
  ["~Ok, tới mẹo thứ ba là", "báo cáo thành podcast."],
  ["Bảo Gemini nghiên cứu một chủ đề", "~nhưng đừng chạy ngay."],
  ["Bắt nó hỏi ngược lại bạn", "trước tới khi đủ hiểu."],
  ["Xong báo cáo đưa vào notebook", "~chọn Audio Overview."],
  ["Nó trả về một tập podcast", "dựng từ chính nghiên cứu của bạn."],
  ["Nghe lúc chạy bộ, lúc lái xe", "~không tốn thêm đồng nào."],
  ["~Và cuối cùng mẹo thứ tư", "nó làm việc khi bạn đang ngủ."],
  ["Nối lịch và email vào Gemini", "~rồi bật Spark"],
  ["đêm nó đọc hết thư đến.", "~Sáng bạn dậy đã có sẵn"],
  ["một bản tóm tắt trong Google Docs."],
  ["Nó dọn được cả", "thư mục lộn xộn trên máy."],
  ["Nhưng cất giấy tờ ngân hàng", "với hồ sơ cá nhân ra chỗ khác trước đã."],
  ["Nghe hay đúng không?", "~Nhưng ít ai nói ra điều này."],
  ["Gemini ổn ở mọi mặt", "và không xuất sắc ở mặt nào."],
  ["Đi rộng không đồng nghĩa", "với đi sâu."],
  ["~OK, như vậy là bốn mẹo vừa rồi", "là phần dễ nhất."],
  ["Sáu mẹo còn lại", "Gems, Skills, Canvas,", "~cách chọn model", "~cho khỏi cháy hạn mức"],
  ["nằm trong bản đầy đủ trên kênh."],
  ["Bấm xem rồi quay lại", "nói tôi biết", "bạn dựng cái nào trước."],
];

// Chip chương trên đầu video — [cardIndexBắtĐầu, nhãn]
export const SECTIONS = [
  [0,  "BẠN ĐANG TRẢ TIỀN CHO NÓ"],
  [3,  "1 · DẠY NÓ CÃI LẠI"],
  [9,  "2 · HỎI 5 TAB CÙNG LÚC"],
  [14, "3 · BÁO CÁO → PODCAST"],
  [20, "4 · NÓ LÀM KHI BẠN NGỦ"],
  [26, "SỰ THẬT"],
  [29, "CÒN 6 MẸO NỮA"],
];
