# Phase 2A — Kịch bản + Giọng + Timeline (Spec thiết kế)

**Ngày:** 2026-09-03
**Trạng thái:** Đã duyệt thiết kế, chờ viết plan
**Thuộc:** Phase 2 (video pipeline) của dự án AI Social Automation. Xem [Phase 1 spec](2026-09-03-ai-social-automation-phase1-design.md).

---

## 1. Mục tiêu

Từ **1 tin đã chọn ở Phase 1** (`Candidate` + `PostContent`), tự động sinh ra bộ input để Remotion render thành 1 video dọc ~40 giây theo đúng phong cách kênh "A Hít Official" (kinetic typography):

- `video/tools/cards.mjs` — `CARDS` (câu chia thành card/line) + `SECTIONS` (chip chương)
- `video/tools/variants.mjs` — `LAYOUT` (variant/anchor/motion từng card)
- `video/public/voice.mp3` — giọng **clone của người dùng** đọc kịch bản
- `video/ref/silence.txt` — kết quả `ffmpeg silencedetect`
- `video/src/timeline.json` — do `video/tools/align.mjs` (có sẵn, không sửa) tạo ra

**Định nghĩa "xong" của 2A:** chạy `python -m pipeline.video.build_video` (có key) tạo đủ 5 nhóm file trên, và `cd video && npx remotion render CodexShort out/smoke.mp4 --frames=0-30` chạy không lỗi.

**Ngoài phạm vi 2A:**
- Lịch nền `BgVideo.BG` tự động, render đầy đủ, gửi Telegram duyệt → **2B**.
- Đăng YouTube / TikTok / FB+IG Reels → **2C**.
- Video ngang dài cho YouTube; nhiều video/ngày.

---

## 2. Bối cảnh & quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Hình dạng quy trình | Tự động hoàn toàn, nối tiếp Phase 1. Không cần đưa gì mỗi ngày (trừ duyệt). |
| Mẫu giọng | Clone **một lần** từ `assets/voice/sample.wav` người dùng thu (3–10 phút). |
| Nơi chạy TTS | CPU ngay trên runner GitHub Actions. Fallback: HF Space (ZeroGPU free). |
| Model TTS | **GPT-SoVITS** (license MIT, dùng thương mại được) làm chính; **F5-TTS tiếng Việt** làm fallback. |
| Định dạng video | Dọc 9:16, 1080×1920, 30fps, **~35–45 giây** (~110–140 từ tiếng Việt). Một file dùng chung Shorts/TikTok/Reels. |
| Khâu dựng video | **Tái dùng** dự án Remotion sẵn có, không dựng lại. 2A chỉ "nạp liệu". |
| Bố trí repo | Gộp dự án Remotion vào `D:\Automation Social\video\`. Một repo, một bộ workflow. |
| `LAYOUT` | LLM tự chọn variant/anchor/motion khi viết kịch bản; **heuristic hậu kiểm** sửa lại cho đúng luật. |
| Căn giờ | Dùng `align.mjs` sẵn có (silence-based). **Không** dùng whisper để căn. |

### Hệ thống Remotion sẵn có (đã khảo sát, ở `D:\video ahitofficial short`)

- `src/KineticShort.tsx` — composition 1080×1920@30. Layers: `BgVideo` (video nền + scrim) → `Stage` (các `CardView` + `Chip` chương + thanh tiến độ) → `Cutouts` (ảnh nổi) → `Audio(voice)` → `Sfx`.
- `src/layouts.tsx` — 8 variant: `stack`, `right` (stack mirror), `hero`, `invert`, `mark`, `stair`, `numeral`, `strike`. Anchor: `top` | `mid` | `low`.
- `src/anim.ts` — `Motion` (vào): `rise` `fall` `slideR` `slideL` `wipe` `pop` `slam`. `Exit` (ra): `up` `down` `dissolve` `shrink` `wipeOut`.
- `tools/cards.mjs` — export `CARDS: string[][]` và `SECTIONS: [number, string][]`. Tiền tố `~` trên 1 line = giữ chỗ tính giờ, không hiện.
- `tools/variants.mjs` — export `LAYOUT: [variant, anchor, num|null, motionIn, motionOut][]`, dài đúng bằng `CARDS`. Comment nội bộ: "hai card liền nhau KHÔNG dùng chung motionVào".
- `tools/align.mjs` — đọc `ref/silence.txt` (ffmpeg silencedetect) + `CARDS` + `LAYOUT`; rải từ vào các đoạn có tiếng theo trọng số âm tiết; xuất `src/timeline.json` `{fps, duration, durationInFrames, cards:[{index, lines:[{text,start,end,hidden}], start, end, out, section, variant, anchor, motion, exit, num?}]}`. Nhận `duration` giây qua `process.argv[2]`.
- `public/` — `bg-*.mp4` (nền), `sfx/`, `cutouts/`, `shots/`, và `voice-*.mp3`.
- `src/Root.tsx` — `<Composition id="CodexShort" durationInFrames={timeline.durationInFrames} fps={timeline.fps} width={1080} height={1920} />`.

---

## 3. Kiến trúc

### 3.1 Thư mục sau khi gộp

```
D:\Automation Social\
├── src/pipeline/                 # Phase 1 (giữ nguyên)
│   ├── run.py                    # + nhánh gọi video khi settings.video.enabled
│   └── video/                    # ★ MỚI — sub-package 2A
│       ├── __init__.py
│       ├── models.py             # Script, Card, SectionMark dataclasses
│       ├── script.py             # LLM → Script
│       ├── variants.py           # heuristic hậu kiểm / chuẩn hoá
│       ├── codegen.py            # Script → cards.mjs + variants.mjs (ESM text)
│       ├── tts.py                # GPT-SoVITS → F5-TTS → HF Space
│       ├── align.py              # ffmpeg silencedetect + node align.mjs
│       └── build_video.py        # orchestrator 2A, cờ --fake / --render-smoke
│
├── video/                        # ★ dự án Remotion, copy từ D:\video ahitofficial short
│   ├── package.json  remotion.config.ts  tsconfig.json
│   ├── src/  (KineticShort.tsx, layouts.tsx, anim.ts, BgVideo.tsx, ... , timeline.json)
│   ├── tools/ (align.mjs giữ nguyên; cards.mjs + variants.mjs bị GHI ĐÈ mỗi lần chạy)
│   ├── public/ (bg-*.mp4, sfx/, cutouts/, voice.mp3 ← ghi vào đây)
│   └── ref/   (silence.txt ← ghi vào đây)
│
├── assets/
│   ├── fonts/BeVietnamPro-Bold.ttf   # Phase 1
│   └── voice/
│       ├── sample.wav               # ★ người dùng thu 1 lần (3–10')
│       └── sample.txt               # transcript mẫu; thiếu → faster-whisper tạo & cache
│
├── config/
│   ├── settings.yaml   # + khối video: {enabled, target_seconds, words_min, words_max, tts_provider}
│   └── voice.yaml      # Phase 1, tái dùng cho giọng văn kịch bản
│
├── data/
│   └── voice_cache/    # sample.txt tự sinh, model manifest, checksum
│
└── output/<ngày>/<id>/video/   # bản sao input đã sinh (cards.mjs, timeline.json, voice.mp3, script.json)
```

`.gitignore` thêm: `video/node_modules/`, `video/out/`, `video/.remotion/`, `data/voice_cache/*.wav`.

### 3.2 Kiểu dữ liệu — `src/pipeline/video/models.py`

```python
@dataclass
class Card:
    lines: list[str]            # phần tử bắt đầu bằng "~" = hidden filler
    variant: str                # stack|right|hero|invert|mark|stair|numeral|strike
    anchor: str                 # top|mid|low
    motion_in: str              # rise|fall|slideR|slideL|wipe|pop|slam
    motion_out: str             # up|down|dissolve|shrink|wipeOut
    num: int | None = None      # cho variant "numeral"

    @property
    def spoken(self) -> str:    # ghép mọi line, bỏ dấu "~", để đưa vào TTS
        ...

@dataclass
class SectionMark:
    label: str                  # IN HOA, ≤ 24 ký tự — nhãn chip
    card_start: int             # index card mở đầu section

@dataclass
class Script:
    cards: list[Card]
    sections: list[SectionMark]   # phần tử đầu phải có card_start == 0
    @property
    def spoken_text(self) -> str: # xuống dòng giữa các card → TTS đọc có nhịp nghỉ
        ...
    @property
    def word_count(self) -> int:  # đếm từ hiển thị (bỏ line "~")
        ...
```

`VALID_VARIANTS`, `VALID_ANCHORS`, `VALID_MOTION_IN`, `VALID_MOTION_OUT` là các `frozenset` hằng trong module.

### 3.3 `script.py`

```python
def build_prompt(cand: Candidate, post: PostContent, voice: dict, cfg: dict) -> tuple[str, str]
def generate(cand, post, voice, cfg, llm=pipeline.llm.generate) -> Script   # raise VideoScriptError
```

- Prompt yêu cầu LLM trả **JSON đúng schema §3.2**: `{sections:[{label, card_start}], cards:[{lines, variant, anchor, motion_in, motion_out, num?}]}`.
- Ràng buộc trong prompt: tiếng Việt 100%; `words_min`–`words_max` từ nói (mặc định 110–140); 12–18 card; 3–5 section; card đầu (0–3s) là **hook**; card cuối là **câu chốt mạnh**; mỗi line ≤ ~7 từ; chèn line `~cái`/`~thì` khi cần nhịp; bám `angle` + `voice.yaml`; **không bịa số liệu**, số thật thì đặt vào 1 card riêng và set `num`.
- `generate`: gọi `llm` (Claude→Gemini như Phase 1) → `parse_json_response` → dựng `Script`. **Validate**:
  - JSON đủ khoá, `cards` 8–20 phần tử, `sections` 2–6, `sections[0].card_start == 0`, `card_start` tăng dần & < len(cards).
  - `word_count` trong `[words_min-15, words_max+15]` (nới 15 vì TTS/ò đọc). Ngoài dải → **retry 1 lần** kèm câu feedback ("bài đang X từ, cần Y–Z"). Vẫn sai → `VideoScriptError`.
  - variant/anchor/motion không thuộc tập hợp lệ → **không raise**, để `variants.normalize` sửa.
- Ghi `script.json` (dump `Script`) vào `output/<ngày>/<id>/video/`.

### 3.4 `variants.py`

```python
def normalize(script: Script) -> Script   # trả Script mới, thuần, idempotent
```

Quy tắc (áp dụng theo thứ tự):
1. Field rỗng/không hợp lệ → mặc định: `variant="stack"`, `anchor="mid"`, `motion_in="rise"`, `motion_out="up"`.
2. Card có line chứa chữ số (regex `\d`) **và** `num` chưa set → set `num` = số đầu tiên trích được; ép `variant="numeral"`.
3. Card là **card cuối của một section** (index kế tiếp mở section mới, hoặc là card cuối cùng) → nếu `variant` đang là `stack`/`right` thì đổi thành `strike`; card cuối cùng của cả video → `invert`.
4. `anchor`: nếu 3 card liên tiếp cùng anchor → card thứ 3 xoay sang giá trị kế trong `[mid, top, low]`.
5. `motion_in`: nếu trùng card ngay trước → chọn giá trị khác gần nhất trong danh sách theo thứ tự `[rise, slideL, wipe, fall, slideR, pop, slam]`.
6. `motion_out`: nếu `variant in {invert, strike}` và `motion_out == "up"` → `"wipeOut"`.

Chạy `normalize(normalize(s))` phải cho kết quả bằng `normalize(s)` (test idempotent).

### 3.5 `codegen.py`

```python
def render_cards_mjs(script: Script) -> str
def render_variants_mjs(script: Script) -> str
def write(script: Script, video_dir: Path) -> None   # ghi tools/cards.mjs, tools/variants.mjs
```

- Xuất **đúng format ESM** như file hiện có:
  - `cards.mjs`: `export const CARDS = [ ["line", "~filler", ...], ... ];` + `export const SECTIONS = [ [0, "NHÃN"], [7, "NHÃN 2"], ... ];`
  - `variants.mjs`: `export const LAYOUT = [ ['stack','mid',null,'rise','up'], ... ];`
  - Header comment tiếng Việt ngắn ghi "FILE TỰ SINH — đừng sửa tay, xem src/pipeline/video/".
- Chuỗi escape an toàn (dùng `json.dumps` cho từng string rồi ghép), `null` cho `num` khi `None`.
- Sau khi ghi: chạy `node --check tools/cards.mjs` và `node --check tools/variants.mjs`; lỗi cú pháp → `CodegenError`.

### 3.6 `tts.py`

```python
class TTSError(Exception): ...

def ensure_sample_text(sample_wav: Path, sample_txt: Path, cache_dir: Path) -> str
    # đọc sample.txt nếu có; else faster-whisper (model 'small', vi) 1 lần, ghi cache

def synthesize(target_text: str, out_mp3: Path, cfg: dict) -> float
    # trả về độ dài giây; raise TTSError nếu mọi backend fail

# nội bộ — mỗi backend nhận (ref_wav, ref_text, target_text, out_wav)
def _gptsovits(...) -> None
def _f5tts(...) -> None
def _hfspace(...) -> None
```

- Thứ tự backend theo `cfg["tts_provider"]` (`auto` = `[gptsovits, f5tts, hfspace]`; hoặc ép 1 cái).
- `_gptsovits`: gọi script inference của GPT-SoVITS đã cài (đường dẫn qua env `GPTSOVITS_DIR`), chế độ zero-shot: `ref_wav` + `ref_text` + `target_text` → wav. Model pretrained cache qua `actions/cache` (key theo version). CPU, `torch` thread = số vCPU.
- `_f5tts`: F5-TTS checkpoint tiếng Việt (HF `hynt/F5-TTS-Vietnamese-ViVoice` hoặc tương đương; đường dẫn qua env `F5TTS_CKPT`). **Lưu ý license**: checkpoint train trên ViVoice — chấp nhận cho bản đầu, ghi rõ trong README để người dùng tự cân nhắc khi kiếm tiền.
- `_hfspace`: `gradio_client.Client(HF_SPACE_ID)` gọi API 1 Space F5-TTS/GPT-SoVITS công khai; timeout 300s; chịu cảnh "Space đang ngủ" (retry sau 60s, tối đa 2 lần).
- Chuẩn hoá output: 44.1kHz mono, `ffmpeg` convert wav→mp3 (libmp3lame, -q:a 2). Trim khoảng lặng đầu/cuối > 0.8s.
- `--fake` (từ `build_video`): bỏ qua mọi backend, tạo wav **im lặng** dài `len(words) * 0.38s` để test luồng.

### 3.7 `align.py`

```python
def make_silence_txt(voice_mp3: Path, out_txt: Path,
                     noise_db: int = -32, min_silence: float = 0.35) -> float
    # ffmpeg -af silencedetect=noise=<>:d=<> ; parse stderr → ref/silence.txt ; trả duration
def run_aligner(video_dir: Path, duration: float) -> Path
    # node tools/align.mjs <duration> ; kiểm tra src/timeline.json tồn tại & parse được
    # raise AlignError nếu exit≠0 hoặc timeline rỗng
```

- `make_silence_txt` ghi đúng format `align.mjs` mong đợi (các dòng `silence_start:` / `silence_end:` như ffmpeg in ra).
- `run_aligner` chạy trong `cwd=video_dir` (align.mjs dùng đường dẫn tương đối `ref/…`, `src/…`).
- Hậu kiểm `timeline.json`: `len(cards) == len(script.cards)`, `start` không giảm, `duration` trong `[25, 55]` → ngoài dải chỉ **cảnh báo** (đưa flag `timeline_off=true` vào manifest cho 2B hiển thị trong preview).

### 3.8 `build_video.py`

```python
def build(root: Path, cand: Candidate, post: PostContent, now: datetime,
          fake: bool = False, render_smoke: bool = False,
          llm=None) -> dict            # trả manifest, hoặc raise Video*Error
def main(argv=None) -> int             # argparse: --root --fake --render-smoke --story <json>
```

Luồng `build`:
1. `cfg = settings["video"]`; nếu `not cfg["enabled"]` → return `{"skipped": "video.enabled=false"}`.
2. `script = script.generate(cand, post, voice, cfg, llm)` → `script = variants.normalize(script)`.
3. `codegen.write(script, root/"video")`.
4. `ref_text = tts.ensure_sample_text(...)`; `dur = tts.synthesize(script.spoken_text, root/"video/public/voice.mp3", cfg)` (hoặc fake).
5. `sil_dur = align.make_silence_txt(voice.mp3, root/"video/ref/silence.txt")`; `align.run_aligner(root/"video", sil_dur)`.
6. Copy `cards.mjs`, `variants.mjs`, `timeline.json`, `voice.mp3`, `script.json` → `output/<ngày>/<id>/video/`.
7. Nếu `render_smoke`: `npx remotion render CodexShort out/smoke.mp4 --frames=0-30` trong `video/` (chỉ chạy khi Node có sẵn).
8. Trả manifest: `{id, seconds, word_count, cards, sections, timeline_off: bool, voice_path, video_dir, tts_backend}`.

Nối Phase 1: trong `run.build()`, sau `pending = review.build_pending(...)`:
```python
if settings.get("video", {}).get("enabled"):
    try:
        vman = video.build_video.build(root, best, post, now, llm=generate)
        pending["video"] = vman
    except (video.VideoScriptError, video.TTSError, video.AlignError, video.CodegenError) as e:
        log.error("video stage failed: %s", e); _notify(f"Video hôm nay lỗi, chỉ đăng ảnh: {e}")
```
→ Ảnh Phase 1 vẫn đăng bình thường; `pending["video"]` để 2B nhặt.

### 3.9 `config/settings.yaml` — khối mới

```yaml
video:
  enabled: false            # 2A xong bật lên; mặc định tắt để Phase 1 không đổi hành vi
  target_seconds: 40
  words_min: 110
  words_max: 140
  tts_provider: auto        # auto | gptsovits | f5tts | hfspace
```

---

## 4. Spike bắt buộc (Task 1 của plan)

**Trước khi hoàn thiện `tts.py`:** dựng GPT-SoVITS v2 chạy headless trên `ubuntu-latest`, CPU-only, đọc một đoạn ~40s tiếng Việt từ `assets/voice/sample.wav` (mẫu ~5 phút) + `sample.txt`.

- **Đạt** nếu: wall-time job < ~30 phút (kể cả tải model, có cache), file wav nghe rõ tiếng, đúng giọng mẫu ở mức "chấp nhận đăng".
- **Không đạt** → chốt **F5-TTS-VN** làm backend chính trong `tts_provider` mặc định (đổi 1 dòng config), GPT-SoVITS lùi làm fallback; nếu F5-TTS cũng quá chậm/CPU không nổi → `tts_provider: hfspace` mặc định.
- Kết quả spike ghi vào `docs/superpowers/notes/2026-09-03-tts-spike.md` (thời gian, RTF, link file mẫu).

Đây là **cổng quyết định** — các task sau của 2A phụ thuộc kết luận này nhưng không bị chặn hoàn toàn (interface `tts.synthesize` không đổi dù backend nào thắng).

---

## 5. Xử lý lỗi (tổng hợp)

| Tình huống | Hành vi |
|---|---|
| LLM trả JSON hỏng / thiếu khoá | retry 1 lần kèm feedback → `VideoScriptError` |
| Số từ ngoài dải sau retry | `VideoScriptError` |
| variant/anchor/motion lạ | `variants.normalize` sửa im lặng |
| `node --check` cards/variants fail | `CodegenError` |
| GPT-SoVITS lỗi/timeout | thử F5-TTS → HF Space |
| Cả 3 backend TTS fail | `TTSError` |
| HF Space đang ngủ | retry sau 60s ×2 |
| `align.mjs` exit≠0 / timeline rỗng | `AlignError` |
| `timeline.json` duration ngoài 25–55s | tiếp tục, `timeline_off=true` trong manifest |
| Bất kỳ `Video*Error` nào trong `run.build` | log + Telegram "chỉ đăng ảnh", Phase 1 tiếp tục |
| Thiếu `assets/voice/sample.wav` | `TTSError` ngay từ `ensure_sample_text`, báo Telegram hướng dẫn |

---

## 6. Test

**pytest** (Python), chạy offline, không mạng, không Node trừ các test đánh dấu `needs_node`.

- `test_video_models.py`: `Card.spoken` bỏ `~`; `Script.word_count` đếm đúng; `spoken_text` có xuống dòng giữa card.
- `test_video_script.py`: inject fake LLM trả JSON mẫu (`tests/fixtures/video_script.json`) → `Script` đủ card/section; JSON thiếu khoá → `VideoScriptError`; số từ 40 → retry được gọi (fake LLM lần 2 trả bản 120 từ) → OK.
- `test_video_variants.py`:
  - card có `"2000 lính"` → `variant=="numeral"`, `num==2000`.
  - không có 2 card kề nhau trùng `motion_in`.
  - card cuối section stack → `strike`; card cuối video → `invert`.
  - `normalize(normalize(s)) == normalize(s)`.
- `test_video_codegen.py`: `Script` cố định (`tests/fixtures/video_script_norm.json`) → khớp **byte-for-byte** với `tests/fixtures/expected_cards.mjs` + `expected_variants.mjs`; `needs_node`: `node --check` cả hai.
- `test_video_align.py` (`needs_node` + ffmpeg): `tests/fixtures/voice_fixture.wav` (~6s, 3 quãng nói) + `cards.mjs` 3 card → `make_silence_txt` ra ≥2 quãng; `run_aligner` → `timeline.json` 3 card, `start` tăng dần, `duration` ≈ 6 ±1.
- `test_video_tts.py`: monkeypatch `_gptsovits` raise → `_f5tts` được gọi; cả ba raise → `TTSError`; `ensure_sample_text` đọc `sample.txt` có sẵn không gọi whisper; `--fake` path tạo wav đúng độ dài ±20%.
- `test_video_build.py`: fake LLM + `fake=True` → `build()` ghi `video/tools/cards.mjs`, `video/src/timeline.json`, `video/public/voice.mp3`, `output/.../video/script.json`; manifest có `word_count`, `cards`, `tts_backend=="fake"`.
- **E2E offline**: `python -m pipeline.video.build_video --fake --story tests/fixtures/story.json` → exit 0, đủ file, `node --check` pass (nếu có Node).
- **CI job riêng** (`video-smoke`, `needs_node`): `cd video && npm ci && npx remotion browser ensure && npx remotion render CodexShort out/smoke.mp4 --frames=0-30` — bắt lỗi Remotion vỡ do cards/variants sinh sai.

Fixtures cố định trong `tests/fixtures/`: `video_script.json`, `video_script_norm.json`, `expected_cards.mjs`, `expected_variants.mjs`, `voice_fixture.wav`, `story.json`, `sample_ref.wav` (2s), `sample_ref.txt`.

---

## 7. Bảo mật & license

- **F5-TTS checkpoint tiếng Việt** train trên ViVoice — license dữ liệu không hoàn toàn rõ cho mục đích thương mại. Dùng làm fallback, **ghi cảnh báo trong README**; GPT-SoVITS (MIT) là đường ưu tiên cho kênh kiếm tiền.
- Mẫu giọng `assets/voice/sample.wav` là dữ liệu cá nhân → repo **private** (đã vậy từ Phase 1). Không commit file wav lớn nếu > 50MB — hướng dẫn nén hoặc để `data/voice_cache/` (gitignored) + tải từ nơi khác qua secret URL.
- Secrets mới có thể cần (2A): `HF_TOKEN` (nếu tải checkpoint gated / gọi Space private). GPT-SoVITS pretrained thường tải công khai, không cần token.
- Không đăng gì ở 2A (đó là 2C) → không có rủi ro outbound.

---

## 8. Giới hạn đã biết

- GPT-SoVITS trên CPU có thể chậm (RTF > 1) → job dài; spike sẽ đo. Nếu > 30 phút thường xuyên → chuyển HF Space.
- `align.mjs` là silence-based: nếu TTS đọc liền không nghỉ giữa câu, việc chia card có thể lệch nhịp. Giảm rủi ro bằng cách `spoken_text` chèn xuống dòng + dấu chấm giữa các card để TTS ngắt hơi; tinh chỉnh `noise_db`/`min_silence` trong spike.
- LLM có thể sinh kịch bản "nhạt" hoặc sai variant → heuristic hậu kiểm chỉ sửa được lỗi cơ học, không sửa được nội dung; bước duyệt Telegram ở 2B là chốt chặn.
- Remotion render đầy đủ (không phải 2A) cần Chromium ~200MB + thời gian; để 2B lo, 2A chỉ smoke 30 frame.
- Chỉ 1 video/ngày, dọc ngắn. Bản dài YouTube là scope khác.

---

## 9. Phụ thuộc sang 2B / 2C

- **2B** đọc `pending["video"]` (manifest §3.8) → sinh `video/src/BgVideo.tsx` `BG` từ `sections` + pool `video/public/bg-*.mp4` → `npx remotion render` đầy đủ → đính MP4 vào preview Telegram (Phase 1 `review`/`approve` mở rộng thêm nút cho video).
- **2C** đọc MP4 đã duyệt → YouTube Data API (resumable upload) + FB `/{page}/video_reels` + IG `media_type=REELS` + TikTok Content Posting API (chưa audit → đăng chế độ nháp/riêng tư, báo Telegram để người dùng bấm đăng tay trong app).

---

## 10. Cần người dùng chuẩn bị (trước khi chạy thật)

1. `assets/voice/sample.wav` — 3–10 phút giọng kể tự nhiên, WAV mono 44.1kHz, phòng yên tĩnh, nội dung giống văn phong kể tin công nghệ. Kèm `assets/voice/sample.txt` (lời thoại) nếu có sẵn — không thì pipeline tự transcribe.
2. Xác nhận pool nền `video/public/bg-*.mp4` (2B dùng, 2A không).
3. (Nếu spike chốt HF Space) tạo `HF_TOKEN` + chọn Space.
