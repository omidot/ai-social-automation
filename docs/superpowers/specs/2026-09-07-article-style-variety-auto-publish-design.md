# P1.5 — Style ảnh đa dạng + tự đăng theo lịch

**Ngày:** 2026-09-07
**Trạng thái:** đã duyệt thiết kế, chờ review spec → writing-plans
**Nhánh dự kiến:** `feature/p1-style-autopublish`
**Base:** `83227ae` (feat(p1): launch-news first with topic-bank fallback; logo-lockup slides...)

## Mục tiêu

Chốt hẳn nhánh bài viết để chạy hoàn toàn tự động, không cần chạm tay vào GitHub và không cần duyệt Telegram:

1. **Bỏ cổng duyệt Telegram** → `draft()` tự lên lịch đăng ngay khi tạo xong; Telegram chỉ còn báo tin + một nút "Gỡ bài" làm lưới an toàn.
2. **Đa dạng style ảnh** → thay vì một khuôn cố định (hook tối + item sáng như `83227ae`), xoay vòng qua 24 style khác nhau, mỗi bài một style, tất cả vẫn thuần Pillow (không AI ảnh, không cutout, không ảnh stock).

Ngoài phạm vi: pipeline video (Phase 2, brainstorm riêng sau).

---

## 1. Bỏ cổng duyệt → tự đăng theo lịch

### 1.1 Luồng mới

Hiện tại: `article_run.draft()` ghi state `status="draft"` + `send_preview()` với 3 nút; toàn bộ việc gọi Meta nằm ở `article_approve.handle_callback` khi người dùng bấm nút.

Mới: `draft()` tạo nội dung + ảnh xong thì **tự lên lịch luôn**, qua một module dùng chung mới `src/pipeline/publish.py`.

```
draft(slot):
    ... tạo article + build_images như cũ ...
    ds.put(date, slot, status="publishing", format=, title=, text_fb=, text_ig=,
           hashtags=, images=, image_urls=, risk=, slot_ict=, sources=, angle=,
           style=<tên style đã dùng>)          # in-flight marker TRƯỚC khi gọi Meta
    publish.schedule_slot(ds, meta, root, date, slot, now)
```

`publish.schedule_slot(ds, meta, root, date, slot, now) -> str`:

```
slot = ds.get(date, slot_name)
when = slot_unix(date, slot["slot_ict"])          # dùng lại từ article_approve
fbids = [meta.fb_upload_photo(root / p) for p in slot["images"]]
fb = meta.fb_create_post(_fb_message(slot), fbids,
                         scheduled_publish_time=when, now_unix=int(now.timestamp()))
if fb["scheduled"]:
    ds.put(..., fb_post_id=fb["id"],
           ig_due=<ISO của when>, result={"fb": fb, "ig": None})
    ds.set_status(date, slot_name, "scheduled")
    tg.send_message(f"🗓 Đã lên lịch {slot_ict}: {title}\n{fb['url']}",
                    buttons=[("🗑 Gỡ bài", f"art:{date}:{slot_name}:undo")])
    return f"scheduled:{date}:{slot_name}"
else:
    # quá sát giờ (<600s) — FB đã đăng luôn; đăng IG ngay
    ig = try meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
    ds.put(..., result={"fb": fb, "ig": ig})
    ds.set_status(date, slot_name, "posted")
    tg.send_message(f"✅ Đã đăng {slot}: {title}\n{fb['url']}" + (" (IG lỗi)" if not ig["ok"] else ""),
                    buttons=[("🗑 Gỡ bài", f"art:{date}:{slot_name}:undo")])
    return f"posted:{date}:{slot_name}"
```

Vì `article-morning` chạy 07:00 ICT (`cron 0 0 * * *`) cho slot 11:30 và `article-evening` chạy 17:00 ICT (`cron 0 10 * * *`) cho slot 19:45, lead time luôn > 600s → nhánh `scheduled` là mặc định. FB tự đăng đúng giờ (lịch native). `article-publish-ig` (đã có) đăng carousel IG khi `ig_due` tới.

### 1.2 Xử lý lỗi khi lên lịch

`schedule_slot` **không** tự nuốt lỗi Meta. `draft()` bọc lời gọi:

```
try:
    publish.schedule_slot(...)
except Exception as e:
    ds.set_status(date, slot, "draft")     # để article-approve thử lại
    _notify_failure(slot, e)               # "❌ Pipeline lỗi (slot): ..." — đã có
    return {"slot": slot, "status": "error"}
```

Đặt lại `status="draft"` (không phải `error`) để **lưới an toàn ở `article-approve`** nhặt lại — xem 1.4. Nếu `fb_create_post` đã tạo post rồi mới lỗi ở bước sau, `fb_post_id` chưa kịp ghi vào state; `schedule_slot` phải theo dõi `fb` cục bộ giống `handle_callback` hiện tại và khi `fb is not None` thì ghi `status="posted"` + `result` (không để `draft`, tránh đăng trùng).

### 1.3 `article_approve` — bỏ nhánh duyệt, thêm nhánh `undo`

`ACTIONABLE` không còn ý nghĩa cũ. `handle_callback` xử lý đúng một action mới:

```
if action == "undo":
    slot = ds.get_safe(date, slot_name)
    if slot is None or slot["status"] in {"discarded"}:
        _ack("Không có gì để gỡ."); return
    when = slot_unix(date, slot["slot_ict"])
    if now.timestamp() - when > 15 * 60:
        _ack("Đăng lâu rồi — vào trang gỡ tay.")
        tg.send_message(f"⚠️ {date}:{slot_name} đã đăng quá 15 phút, gỡ thủ công trên FB/IG.")
        return f"undo-expired:{date}:{slot_name}"
    res = slot.get("result") or {}
    fb_id = (res.get("fb") or {}).get("id") or slot.get("fb_post_id")
    ig_id = (res.get("ig") or {}).get("media_id")
    if fb_id: try meta.fb_delete_post(fb_id)
    if ig_id: try meta.ig_delete_media(ig_id)
    ds.set_status(date, slot_name, "discarded")
    _ack("Đã gỡ."); tg.send_message(f"🗑 Đã gỡ {date}:{slot_name} khỏi FB/IG.")
    return f"discarded:{date}:{slot_name}"
```

Nhánh `now` / `sched` / `drop` cũ: **xóa**. Test tương ứng: xóa/viết lại.

Cửa sổ "15 phút" tính từ giờ slot (`slot_ict`), không phải từ lúc bấm — với slot buổi sáng, người dùng có từ 07:00 (lúc nhận tin đã-lên-lịch) đến 11:45 để bấm Gỡ; sau 11:45 thì API xóa vẫn chạy được nhưng ta từ chối cho đơn giản và nhất quán.

### 1.4 `article_approve.poll` — lưới an toàn lên lịch lại

Thêm một quét trong `poll()` sau `expire_stale`: mọi slot `status="draft"` có `images` + `text_fb` đã sẵn (tức `draft()` đã tạo nội dung nhưng `schedule_slot` lỗi) và **`now < giờ slot`** → gọi `publish.schedule_slot` lại. Khi `now >= giờ slot` mà vẫn `draft` → `expire_stale` chuyển `expired` **ngay** (không chờ 24h nữa) + cảnh báo Telegram `⚠️ {slot} không lên lịch được, đã bỏ`. Quy tắc 24h cũ cho `draft` bỏ đi vì không còn nút duyệt tay để chờ.

Đây là đường phục hồi duy nhất còn lại sau khi bỏ nút bấm tay, nên phải có test.

### 1.5 `meta.py` — thêm xóa bài

```
def fb_delete_post(self, post_id: str) -> dict:
    r = self._client.delete(f"{BASE}/{post_id}", params={"access_token": self.token})
    _raise_for_graph(r); return r.json()

def ig_delete_media(self, media_id: str) -> dict:
    r = self._client.delete(f"{BASE}/{media_id}", params={"access_token": self.token})
    _raise_for_graph(r); return r.json()
```

(IG Content Publishing cho phép `DELETE /{ig-media-id}`. Nếu Graph từ chối xóa IG, `try/except` nuốt và vẫn báo người dùng phần FB đã gỡ.)

---

## 2. Hệ thống style — thuần Pillow, 24 style

### 2.1 `config/styles.yaml`

Danh sách 24 entry. Mỗi entry:

```yaml
- name: navy-centered
  layout: centered          # 1/6: centered | left-rail | bottom-bar | split | magazine | ticket
  palette: white-on-navy    # 1/4: ink-on-white | white-on-navy | warm-editorial | mono-contrast
  font: grotesk             # 1/4: grotesk | editorial | mono | rounded
  texture: dots             # 1/5: dots | grid | diagonal | plain | gradient-band
  accent_shape: underline   # 1/4: underline | bar | bracket | none
  logo: tile                # 1/3: tile | chip | mono
```

Không còn field nào liên quan AI. 24 entry = 6 layout × 4 palette, mỗi tổ hợp gán font/texture/accent_shape/logo sao cho nhìn tách bạch. Danh sách 24 cụ thể viết trong plan.

### 2.2 Bảng màu (`PALETTES` trong `styles.py`)

| tên | bg | ink | accent | muted | ghi chú |
|---|---|---|---|---|---|
| `ink-on-white` | `#F4F5F7` | `#111111` | `#1D4ED8` | `#6B7280` | mặc định sáng |
| `white-on-navy` | `#0B1B3A` | `#FFFFFF` | `#6EA8FE` | `#93A4C4` | tối xanh |
| `warm-editorial` | `#F3ECE2` | `#241E1A` | `#B4472E` | `#8A7C6C` | kem / gạch |
| `mono-contrast` | `#0A0A0A` | `#FAFAFA` | `#FAFAFA` | `#9A9A9A` | đen trắng |

Mỗi palette có thêm `on_accent` (màu chữ khi nằm trên nền accent) suy ra tự động (trắng nếu accent tối, `#0A0A0A` nếu accent sáng).

### 2.3 Font — bundle vào `assets/fonts/`

| key | họ | file | dùng cho |
|---|---|---|---|
| `grotesk` | Be Vietnam Pro | `BeVietnamPro-{Regular,Bold,ExtraBold}.ttf` | mặc định |
| `editorial` | Lora | `Lora-{Regular,Bold}.ttf` + `Lora-Italic.ttf` | layout `magazine` |
| `mono` | JetBrains Mono | `JetBrainsMono-{Regular,Bold}.ttf` | layout kỹ thuật |
| `rounded` | Nunito | `Nunito-{Regular,Bold,ExtraBold}.ttf` | style mềm |

Tất cả OFL, có bộ dấu tiếng Việt đầy đủ. `media.FONT_PATH` hiện tại giữ nguyên làm fallback cuối. `styles.font_paths(key) -> {"regular":.., "bold":.., "black":.., "italic":..}` với fallback về grotesk rồi về `media.FONT_PATH` nếu file thiếu.

### 2.4 `src/pipeline/styles.py`

```
load_styles(root) -> list[Style]      # đọc + validate config/styles.yaml, đúng 24, field hợp lệ
Style: dataclass(name, layout, palette:dict, font:str, texture:str, accent_shape:str, logo:str)
pick_style(root, now) -> Style        # xoay vòng
```

`pick_style`:
- đọc `data/style_cursor.json` = `{"recent": ["navy-centered", ...]}` (mới nhất ở đầu, tối đa 15).
- chọn style đầu tiên trong `load_styles` **không** nằm trong `recent`; nếu tất cả đều nằm (danh sách < 16) thì lấy cái cũ nhất.
- ghi lại `recent` (chèn đầu, cắt 15), lưu file. File nằm trong `data/` nên `commit_state.sh` tự commit.
- Không phụ thuộc `now` để chọn (tham số giữ cho khả năng test / tương lai); xoay thuần theo con trỏ.

### 2.5 `src/pipeline/images.py`

Tái cấu trúc: tách phần "vẽ gì" khỏi "vẽ ở đâu".

```
build_images(article, out_dir, *, size, brand=None, root=None, style=None) -> list[str]
```

- `style = style or styles.pick_style(root, now_utc())`.
- Với mỗi slide (hook / item×N / close), dựng `SlideModel` trung gian (đã có sẵn logic tạo nội dung slide từ `article.slides`) rồi gọi `LAYOUTS[style.layout](canvas, role, slide_model, style, brand, ctx)`.
- `LAYOUTS: dict[str, Callable]` — 6 hàm:
  - `_layout_centered` — mọi thứ căn giữa; logo-lockup trên-giữa; headline giữa khung; body dưới headline; handle chân giữa; CTA "Vuốt tiếp ›" chân phải.
  - `_layout_left_rail` — dải màu `accent` dọc mép trái ~10%; nội dung căn trái sát dải; logo trên-trái; số thứ tự lớn mờ nằm trong dải.
  - `_layout_bottom_bar` — 55% trên: glyph/again số thứ tự cực lớn màu mờ + logo; 45% dưới: khối `accent` đặc, chữ màu `on_accent`, headline + body nằm trong khối.
  - `_layout_split` — nửa trên nền `accent` nhạt (tint) chứa kicker + headline; đường kẻ ngang đậm; nửa dưới nền `bg` chứa body + logo-lockup + handle.
  - `_layout_magazine` — ép `font=editorial`; kicker chữ hoa nhỏ giãn cách; hai đường chỉ mảnh trên/dưới headline; lề rộng; body hai cột nếu > 6 dòng; drop-cap chữ đầu.
  - `_layout_ticket` — thẻ bo góc inset ~64px, viền nét đứt, hàng chấm đục lỗ chia "cuống"; headline + body trong thân thẻ; handle + số thứ tự ở cuống; texture nền ngoài thẻ.
- `ctx` mang: danh sách logo path (hook), logo+tên công cụ (item), tổng số slide, chỉ số slide, `_fetch_logo`, `_ICONS`.
- Mọi layout **bắt buộc** vẽ: (item) logo + tên thương hiệu công cụ; (hook) toàn bộ logo các công cụ; handle `A Hít Official`; (item/hook) gợi ý vuốt; body 40–70 chữ (đã do writer đảm bảo, layout chỉ cần không cắt).
- `texture`: `_draw_texture(canvas, kind, palette)` — `dots` (lưới chấm mờ), `grid` (kẻ ô mảnh), `diagonal` (gạch chéo thưa), `plain` (không gì), `gradient-band` (dải chuyển màu bg→accent rất nhạt ở một cạnh).
- `accent_shape`: helper `_accent_under(draw, box, kind, color)` — `underline` (gạch 4px), `bar` (khối đặc sau headline), `bracket` (hai ngoặc góc), `none`.
- `logo`: `tile` (ô trắng bo góc — như v4), `chip` (nền `accent`, glyph/logo đảo màu), `mono` (logo khử màu về 1 tông `ink`).

### 2.6 Fallback

`build_images` giữ nguyên khung `try → fallback`:
- Nếu `LAYOUTS[...]` cho một slide ném lỗi → slide đó vẽ bằng renderer v4 hiện tại (`_render_hook_slide` / `_render_item_slide` đổi tên thành `_fallback_hook` / `_fallback_item`, giữ y nguyên code) với palette của style.
- Nếu `pick_style` / `load_styles` lỗi (YAML hỏng) → dùng style mặc định cứng `navy-centered` tương đương v4.
- Nếu cả `build_images` ném → khung fallback tổng hiện có (ảnh phẳng 1080×1350) vẫn chạy.

Ảnh luôn ra đủ số lượng, đúng 1080×1350, không bao giờ làm gãy `draft()`.

### 2.7 Ghi `style` vào state

`draft()` truyền `style` (đã `pick_style` một lần) vào `build_images` **và** ghi `style=<name>` trong `ds.put(...)`, để (a) debug, (b) `topics.recent_titles` / báo cáo sau này biết bài nào style nào.

---

## 3. Test

| File | Thêm / sửa |
|---|---|
| `tests/test_styles.py` (mới) | `load_styles` đọc đúng 24, mọi `layout∈6`, `palette∈4`, `font∈4`, `texture∈5`, `accent_shape∈4`, `logo∈3`; tên không trùng. `pick_style` xoay vòng: gọi 24 lần ra 24 tên khác nhau; lần 25 = lần 1; không lặp trong 15; con trỏ ghi/đọc đúng từ `data/style_cursor.json` (dùng `tmp_path`). |
| `tests/test_images.py` (mở rộng) | Với `_fetch_logo` monkeypatch trả `None` và một `ArticleContent` fixture: mỗi trong 6 layout, cho role `hook` / `item` / `close`, `build_images(style=<đó>)` ra file 1080×1350, số lượng = số slide, không ném. Ép một layout ném → slide đó rơi về `_fallback_*`, ảnh vẫn ra. `load_styles` hỏng → `navy-centered` mặc định. |
| `tests/test_meta.py` (mở rộng) | `fb_delete_post` / `ig_delete_media` gọi `DELETE /{id}` với `access_token`, `_raise_for_graph` chạy; 4xx → `MetaError`. |
| `tests/test_publish.py` (mới) | `schedule_slot`: nhánh `scheduled` (lead > 600s) ghi `status="scheduled"` + `fb_post_id` + `ig_due` + gửi tin có nút `undo`; nhánh `posted` (lead < 600s) đăng IG + `status="posted"`; lỗi trước khi `fb` tạo → ném ra ngoài (không nuốt), state chưa chuyển `scheduled`; lỗi sau khi `fb` tạo → `status="posted"` + `result.ig.ok=False`. |
| `tests/test_article_run.py` (sửa) | `draft()` gọi `schedule_slot`; thành công → `status="scheduled"`, `style` có trong state; `schedule_slot` ném → `status="draft"` + `_notify_failure`. Bỏ mọi assert về 3 nút preview. |
| `tests/test_article_approve.py` (viết lại) | Bỏ test `now`/`sched`/`drop`. Thêm: `undo` trong cửa sổ 15' gọi `fb_delete_post` + `ig_delete_media` → `status="discarded"`; `undo` quá hạn → từ chối, state không đổi; `poll()` nhặt slot `draft` có nội dung sẵn & `now < giờ slot` → gọi `schedule_slot` lại; `expire_stale` khi `now >= giờ slot` vẫn `draft` → `expired` ngay + cảnh báo. |
| `tests/test_workflows.py` (sửa nếu cần) | `article-approve.yml` vẫn `*/5`, vẫn `concurrency.group: pipeline-state`; không có secret mới. |

Full `pytest tests --ignore=tests/video -q` phải xanh. CI-parity (`article-test.yml`) xanh.

---

## 4. Không làm (YAGNI)

- Không AI tạo ảnh, không cutout nhân vật, không ảnh stock / Unsplash.
- Không dashboard / lệnh chọn style tay; không ghi đè style qua Telegram.
- Không A/B test style, không lưu lịch sử ảnh, không thống kê hiệu quả theo style.
- Không đổi lịch cron, không đổi `settings.yaml` slots.
- Không giữ lại nút "Đăng ngay" / "Lên lịch" — chỉ còn "Gỡ bài".
- Không webhook (vẫn polling `*/5`).

---

## 5. Rủi ro / lưu ý

- **Bỏ duyệt = nội dung lên thẳng trang.** Người dùng đã chọn có ý thức (2026-09-07). Lưới an toàn: `risk:true` từ writer vẫn ghi vào state và vào tin Telegram; nút "Gỡ bài" 15'; `_ARTICLE_GUARDRAILS` trong `write.py` giữ nguyên.
- **Token Meta hết hạn giữa chừng** → `schedule_slot` ném → slot về `draft` → `article-approve` thử lại 5' rồi 24h sau `expired` + loạt cảnh báo Telegram. Không đăng sai, chỉ mất slot.
- **`fb_create_post` scheduled cần lead ≥ 600s** — đã có branch xuống "đăng ngay" nếu sát giờ; với cron 07:00/15:00 gần như không chạm.
- **IG không lên lịch native** — vẫn phụ thuộc `article-publish-ig` poller chạy đúng khung giờ cron của nó (`0,15,30,45 4,5,12,13 * * *` UTC). Kiểm tra khung này phủ 11:30 và 19:45 ICT (= 04:30 và 12:45 UTC) — OK.
- **24 style thuần Pillow** là khối code layout không nhỏ; 6 hàm layout mỗi hàm tự chứa, test từng cái từ fixture để giữ kiểm soát.
