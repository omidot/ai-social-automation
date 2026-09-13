# Video: thẻ biểu đồ + thẻ chụp màn hình web, đổi giao diện chữ

**Ngày:** 2026-09-13
**Trạng thái:** đã duyệt thiết kế, chờ review spec → writing-plans
**Base:** `1e74d57` (nền video 2 đoạn bg1.mp4/bg2.mp4 đã merge)

## 1. Mục tiêu

Kênh đối thủ tham khảo (fanpage "AI News - Tin tức AI mỗi ngày", ainius.net) có phong cách kinetic-typography sắc nét hơn: tiêu đề tương phản in đậm kiểu "KHÔNG PHẢI X MÀ LÀ Y", thẻ số liệu đóng khung nổi bật, biểu đồ động khi so sánh số liệu, và ảnh chụp màn hình trang web thật khi nhắc tới một sản phẩm/repo cụ thể. Việc này thay đổi **lớp hiệu ứng chữ + thêm 2 loại thẻ mới** trong kịch bản video hiện có — không đổi kiến trúc render, không đổi nền video (giữ nguyên bg1.mp4 → bg2.mp4 vừa merge), không đổi luồng thu âm/duyệt.

**"Xong" của tính năng này:** một kịch bản video do LLM sinh ra có thể chứa thẻ chữ thường (giao diện B), thẻ số liệu (giao diện C), thẻ biểu đồ (`chart`), và thẻ chụp màn hình (`screenshot`); render ra MP4 hiển thị đúng cả 4 loại; một lượt chụp màn hình lỗi (mạng, tìm kiếm, timeout) không làm hỏng cả video — thẻ đó tự rớt về giao diện B.

**Ngoài phạm vi:** đổi nền video (đã xong ở nhánh trước). Đổi giọng đọc/thu âm. Cho phép người dùng tự soạn tay từng thẻ. TTS. Chụp màn hình nhiều ảnh trong một thẻ hoặc cuộn trang.

## 2. Bối cảnh & quyết định đã chốt

| Vấn đề | Quyết định (2026-09-13) |
|---|---|
| Thẻ chữ thường (không số liệu) | **Giao diện B**: IN HOA, rất đậm, sans-serif, một cụm từ khoá tô cam/đỏ (`#ff4d2e`), gạch ngang khi so sánh (dùng lại `variant: "strike"` đã có) |
| Thẻ có số liệu thật (`num`) | **Giao diện C**: số nổi bật trong khung viền cam/đỏ, dòng mô tả bên dưới |
| Thẻ biểu đồ (mới) | Cả 3 kiểu — đường / cột 2 giá trị / thanh ngang xếp hạng. **LLM tự chọn kiểu** theo hình dạng dữ liệu khi viết kịch bản |
| Dữ liệu biểu đồ | LLM tự điền khi viết kịch bản (giống cách `num` đang hoạt động) — không có nguồn dữ liệu ngoài |
| Thẻ chụp màn hình (mới) | Giao diện **khung trình duyệt** (thanh địa chỉ + 3 chấm màu, giống clip GitHub trong ảnh tham khảo) |
| Trang web để chụp | LLM tự viết câu tìm kiếm cho từng thẻ (không dùng lại `source_url` của bài — linh hoạt hơn nhưng cần xử lý lỗi kỹ) |
| Cơ chế tìm kiếm | **Google Custom Search API** — cần `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` (secret mới, người dùng tự tạo) |
| Thời điểm chụp ảnh | Ở bước **render** (`render_pending`, sau khi nhận audio) — môi trường đó sẽ được thêm Playwright, không đụng tới `article-morning/evening` |
| Chụp ảnh lỗi | Thẻ đó rớt về giao diện B (thẻ chữ thường), **lời thoại không đổi** (không ảnh hưởng canh thời gian với audio đã thu), video vẫn render tiếp |
| Bắt buộc có biểu đồ/ảnh chụp? | **Không.** 0 hoặc nhiều thẻ mỗi loại, tuỳ nội dung có số liệu/trang web đáng nhắc hay không |

Do bảng số liệu tối đa 4 dòng ở dạng thanh ngang (hbar) và tối thiểu 3 điểm cho biểu đồ đường — xem §3.1.

## 3. Kiến trúc

### 3.1 `src/pipeline/video/models.py` — mở rộng `Card`

```python
@dataclass
class ChartSpec:
    kind: str                        # "line" | "bar" | "hbar"
    items: list[dict]                # line: [{"y": float}, ...] (>=3)
                                      # bar:  [{"label": str, "value": float}] (đúng 2)
                                      # hbar: [{"label": str, "value": float}] (2..4)
    unit: str = ""                   # vd "$", "%", "tok/s" -- hiện cạnh mỗi giá trị

@dataclass
class ScreenshotSpec:
    query: str                       # câu tìm kiếm LLM tự viết, vd "GitHub OpenAI Codex repository"

@dataclass
class Card:
    lines: list[str]
    variant: str
    anchor: str
    motion_in: str
    motion_out: str
    num: int | float | None = None
    chart: ChartSpec | None = None
    screenshot: ScreenshotSpec | None = None
```

Ràng buộc: một card chỉ được set **tối đa một** trong `num` / `chart` / `screenshot`. `to_dict`/`from_dict` mở rộng tương ứng (giữ style hiện có, `from_dict` dùng `_coerce_num` như cũ cho `num`).

### 3.2 `src/pipeline/video/script.py` — prompt + validate

**Prompt** (`build_prompt`) bổ sung:
- Mô tả 2 loại thẻ mới, cho ví dụ JSON shape.
- "Chỉ thêm `chart` khi có ít nhất 2 số liệu THẬT đáng so sánh trong bài. Chỉ thêm `screenshot` khi bài nhắc tới một sản phẩm/repo/trang cụ thể có thể tìm bằng Google. Không bắt buộc mỗi kịch bản phải có 2 loại thẻ này."
- Giữ nguyên yêu cầu hiện có (giữ tên riêng, giải thích thuật ngữ, giọng Iman Gadzhi — không đổi).

**`_validate`** (script.py) bổ sung kiểm tra mỗi card:
- Không được set nhiều hơn 1 trong `num`/`chart`/`screenshot` → `VideoScriptError`.
- `chart.kind` ∈ {line, bar, hbar}; `line` ≥3 items; `bar` đúng 2 items; `hbar` 2..4 items; mọi `item.value` là số.
- `screenshot.query` là chuỗi không rỗng, ≤100 ký tự.

Lỗi validate đã tự động được thử lại 1 lần nhờ cơ chế retry-on-validation-error vừa sửa hôm nay (`fix(video): retry on any validation error`) — không cần thêm gì ở tầng retry.

### 3.3 `src/pipeline/video/screenshot.py` (module mới)

```python
class ScreenshotError(Exception): ...

def search_top_url(query: str, *, api_key: str, cx: str, timeout: int = 10) -> str:
    """Gọi Google Custom Search API, trả URL kết quả đầu tiên.
    Raise ScreenshotError nếu thiếu key/cx, lỗi mạng, hoặc không có kết quả."""

def capture(url: str, out_path: Path, *, timeout_ms: int = 15000) -> None:
    """Playwright (gói Python đã có sẵn, dùng chung với collect.py) mở url,
    chờ load, chụp viewport 1280x800, lưu PNG tại out_path. Runner của
    video-render.yml cần tự cài trình duyệt Chromium riêng (xem §3.7) vì
    workflow này hiện chưa làm việc đó, khác với article-morning/evening.
    Raise ScreenshotError nếu điều hướng/timeout lỗi."""

def search_and_capture(query: str, out_path: Path, *, api_key: str, cx: str) -> str:
    """search_top_url rồi capture. Trả về url đã chụp (để hiện trong thanh địa
    chỉ mock-up). Raise ScreenshotError ở bất kỳ bước nào."""
```

Không có secret (`GOOGLE_CSE_API_KEY`/`GOOGLE_CSE_CX` trống) → `search_and_capture` raise `ScreenshotError` ngay từ đầu, không gọi mạng — nhánh chụp màn hình coi như tắt, giống cách `video.publish.tiktok: false` tắt một nền tảng.

### 3.4 `src/pipeline/video/codegen.py` — mở rộng định dạng vị trí hiện có

`render_variants_mjs` hiện sinh mỗi card thành một **mảng theo vị trí**:
`[variant, anchor, num, motion_in, motion_out]` (xem code hiện tại — không phải object có tên trường). Thêm 2 vị trí mới ở cuối, giữ nguyên style:

```python
chart = "null" if c.chart is None else json.dumps(c.chart.to_dict(), ensure_ascii=False)
shot = "null" if c.screenshot_file is None else _q(c.screenshot_file)
lines.append(
    f"  [{_q(c.variant)}, {_q(c.anchor)}, {num}, "
    f"{_q(c.motion_in)}, {_q(c.motion_out)}, {chart}, {shot}],\n"
)
```

`KineticShort.tsx` phía TS đọc mảng `LAYOUT` theo đúng thứ tự vị trí này (đã làm vậy với `num` từ trước) — thêm destructure 2 phần tử mới `chart`, `screenshotFile` ở cuối mỗi hàng.

### 3.5 `src/pipeline/video/render.py` — gọi chụp ảnh, rớt an toàn

Trong `render_pending()`, `s = Script.from_dict(v["script"])` dựng lại script từ daily-state như hiện tại — **trước** `_codegen.write(s, video_dir)` (codegen cần `screenshot_file` đã có sẵn để ghi vào `variants.mjs`, xem §3.4), với mỗi card có `screenshot`:

```python
for i, card in enumerate(s.cards):
    if card.screenshot is None:
        continue
    shot_path = video_dir / "public" / "screenshots" / f"{i}.png"
    try:
        api_key = os.environ["GOOGLE_CSE_API_KEY"]; cx = os.environ["GOOGLE_CSE_CX"]
        _screenshot.search_and_capture(card.screenshot.query, shot_path,
                                       api_key=api_key, cx=cx)
        card.screenshot_file = f"screenshots/{i}.png"
    except (KeyError, ScreenshotError) as e:
        log.warning("screenshot card %d failed (%s) -- falling back to text card", i, e)
        card.screenshot = None    # render như thẻ chữ thường (giao diện B); lời thoại (lines) không đổi

_codegen.write(s, video_dir)
```

`screenshot_file` là field mới trên `Card` (mặc định `None`), chỉ được set ở đây — tại thời điểm soạn kịch bản (`draft_script.draft`, `write_script_json`) nó luôn `None` nên không cần logic loại trừ riêng khi ghi `script.json` xuống đĩa. `s` ở trên dựng lại **từ `v["script"]` đã lưu trong daily-state mỗi lần gọi**, nên nếu chụp ảnh thất bại và slot quay lại `awaiting_audio` để thử lại (do lỗi *khác*, vd remotion crash), lần render sau vẫn đọc lại `screenshot.query` gốc từ state và thử chụp lại — không bị mất vĩnh viễn.

### 3.6 Remotion (`video/src/`)

- **`Chart.tsx`** (mới): nhận `ChartSpec`, vẽ line (SVG polyline, animate bằng `stroke-dashoffset` theo frame), bar (2 cột, animate chiều cao theo `interpolate(frame, ...)`), hbar (thanh ngang animate chiều rộng) — theo đúng mock-up đã duyệt, dùng `#ff4d2e` làm màu nhấn, nền tối `cur.pal.scrim` giữ nguyên.
- **`Screenshot.tsx`** (mới): khung trình duyệt (thanh địa chỉ hiện domain rút gọn từ url trả về, 3 chấm màu), `<Img src={staticFile(card.screenshotFile)}>` bên trong, fade/slide-in dùng lại vocabulary `motion_in` hiện có.
- **`KineticShort.tsx`**: renderer mỗi card rẽ nhánh `card.chart → <Chart/>`, `card.screenshot_file → <Screenshot/>`, `card.num != null → <NumeralCardStyleC/>` (đổi giao diện, giữ layout cũ), else → `<TextCardStyleB/>` (đổi giao diện, thay cho renderer chữ hiện tại).
- Đổi màu nhấn toàn cục theo `#ff4d2e` cho mọi biến thể chữ đậm/gạch ngang, khớp mock-up đã duyệt.

### 3.7 Workflow / secrets

- `.github/workflows/video-render.yml`: thêm bước cài Playwright (`python -m playwright install --with-deps chromium`) — hiện chưa có, chỉ có Node/Remotion.
- Thêm `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX` vào `env:` của bước "Render + publish" (giống các secret khác, người dùng tự tạo trên Google Cloud Console + GitHub Secrets).

## 4. Kiểm thử

- `tests/video/test_models.py`: `Card`/`ChartSpec`/`ScreenshotSpec` roundtrip; card không được set >1 trong num/chart/screenshot.
- `tests/video/test_script.py`: `_validate` bắt đúng lỗi hình dạng chart (sai `kind`, sai số lượng items cho từng kind, `value` không phải số), lỗi `screenshot.query` rỗng/quá dài; prompt chứa hướng dẫn 2 loại thẻ mới.
- `tests/video/test_screenshot.py` (mới): `search_top_url`/`capture`/`search_and_capture` với `httpx`/Playwright được mock — thành công, API lỗi, không có kết quả, timeout điều hướng; thiếu secret → `ScreenshotError` ngay không gọi mạng.
- `tests/video/test_render.py`: `render_pending` với một script có `screenshot` — chụp thành công (gắn `screenshot_file`, không đổi `v["script"]` đã lưu) và chụp thất bại (rớt về card chữ, render vẫn tiếp tục ra MP4, không lan lỗi lên `_fail()`).
- `video-smoke.yml`/`tests/fixtures/video/story.json`: bổ sung 1 card chart + 1 card screenshot vào fixture; nhánh screenshot trong smoke test dùng URL cục bộ giả (không gọi Google/network thật trong CI) để không phụ thuộc mạng ngoài.

## 5. Rủi ro & lưu ý

- Google Custom Search có hạn 100 lượt tìm miễn phí/ngày — với 2 video/ngày, tối đa vài thẻ chụp màn hình mỗi video, không lo vượt hạn ở quy mô hiện tại; nếu vượt hạn, `search_top_url` trả lỗi và thẻ rớt về giao diện B như bình thường (không phải trường hợp đặc biệt cần xử lý riêng).
- Chụp ảnh trang web thật của bên thứ ba có thể đổi giao diện/nội dung/quảng cáo bất kỳ lúc nào — chấp nhận được vì mục đích là minh hoạ ("đây là trang thật"), không phải tài liệu chính xác tuyệt đối.
- Không cache/tái dùng ảnh chụp giữa các lần render cùng slot (mỗi lần audio gửi lại → chụp lại) — chấp nhận được vì tần suất thấp (vài lần/video).
