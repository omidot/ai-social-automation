# News-first content refresh — fix the scoring gate, broaden the writer, retire the listicle bank

**Status:** design approved 2026-09-09. Base: `master` @ `0dda0ff`.

## 1. Problem

The article pipeline is supposed to prefer **launch-news** content in the channel's
sharp, opinionated "Iman Gadzhi" voice (`article_run.draft` step 1: `collect` RSS →
`score` → `write.write_share`), and only fall back to a curated topic bank
(`config/topics.yaml` → `write.write_topic_post`) when no news survives.

**In practice it falls back 100% of the time.** Every post in `data/daily/` for
2026-09-06…09 has `sources: []` (topic-bank origin) and is a listicle
("N công cụ AI để …" / "Cách dùng AI để …"). Current AI events — e.g. a GPT-6 "Astra"
launch — never appear.

### Root cause

`score.score_candidate` = `_recency(0–40) + _popularity(0–30) + _cross_source(0–20) +
_keyword_fit(0–10) + _source_spread(0–20)`, gated at `articles.min_score = 45`.

- `_popularity` is `0` for every RSS item (only Reddit/HN carry `raw_score_hint`).
- `_cross_source` / `_source_spread` are `0` unless the *same* story appears in ≥2 feeds
  in the same run.
- A first-party AI launch (OpenAI/Anthropic/DeepMind blog), single feed, 24 h old,
  scores `_recency ≈ 20 + _keyword_fit ≈ 7 ≈ 27` — **structurally below 45**.

So a single-source first-party AI launch **can never clear the gate**. Compounding it,
`write.write_share` only accepts a source that is "a big lab that JUST SHIPPED a
product" and returns `{"skip": true}` for anything else (rumor, analysis, funding,
research, benchmark, drama, policy). And the fallback bank is 100% listicle, so every
fallback day is "top AI tools".

## 2. Goals

1. A single-source first-party AI news item, ≤ ~4 days old, **reliably clears** the
   scoring gate and gets written.
2. `write_share` accepts **any AI-relevant news with a fetchable body**, not only
   product launches.
3. The writer produces one of **four angles** — `tin-nong`, `quan-diem`, `xu-huong`,
   `chuyen-thuc-chien` — picking whichever fits the news.
4. The fallback bank is **evergreen opinion + trend** prompts in the Iman voice, never
   listicles.
5. Morning and evening on the same day use **different angles**.
6. First implementation step is a **diagnostic** that confirms (or corrects) the
   root-cause analysis against live feeds before thresholds are changed.

Non-goals: LLM web search (decided against — RSS only); recycling stale news for the
fallback; touching the video pipeline (video scripts derive from the article and
inherit the new voice automatically); rewriting `styles`/`images`.

## 3. The four angles

A single `ANGLES` set, shared by `write_share` (picks per news item) and
`topics.propose_topic` (a fallback topic is born with `quan-diem` or `xu-huong`):

| code | when the writer picks it |
|---|---|
| `tin-nong` | something just happened → "what this news actually teaches us", not a bulletin |
| `quan-diem` | the common take on this is wrong / shallow → a contrarian argument |
| `xu-huong` | this news is one data point in a larger shift → name the shift, what it means for the reader |
| `chuyen-thuc-chien` | there's a concrete, tried application → told as lived experience + a principle |

`ANGLES = {"tin-nong", "quan-diem", "xu-huong", "chuyen-thuc-chien"}` in `write.py`.
The legacy `ALLOWED_ANGLES` / `write_post` / `build_prompt` (an older news-writer not on
the `article_run` path) is left untouched — out of scope, and its tests still pass.

## 4. Changes

### 4.1 Diagnostic (first task, no behaviour change)

Add opt-in verbose logging to `collect` and `score`, gated on an env var
`ARTICLE_DEBUG=1` (default off — normal runs unchanged):

- `collect.collect`: per feed, log `name`, HTTP status, entries parsed, entries within
  `MAX_AGE_HOURS`, entries dropped as stale. On a feed exception, log the feed name +
  error (it is already swallowed per-feed; just make it visible).
- `score.pick_n`: for every candidate, log `title`, `source`, `published_at` age in
  hours, and the five score components + total, plus the reject reason
  (`non-AI` / `below min_score` / `title-blocked` / `no body`).

Run it once with network: `ARTICLE_DEBUG=1 .venv/Scripts/python.exe -m
pipeline.article_run --slot morning --root . --fake-llm` (the fake LLM still writes a
valid storyboard, so the collect+score half runs for real). Capture the output in the
task report. If it contradicts §1 (e.g. feeds are simply down, or nothing AI-relevant
is being published), STOP and re-brainstorm the thresholds. If it confirms §1, proceed
to 4.2 with the real numbers.

### 4.2 Scoring gate (`score.py`, `config/settings.yaml`, `collect.py`)

- `config/settings.yaml` → `articles.min_score: 45` → **`20`**.
- `collect.py` → `MAX_AGE_HOURS = 48` → **`96`**.
- `score.py` → new `_source_tier(c) -> float`, added into `score_candidate`:
  - **+15** if `c.source` (lowercased) contains any of: `openai`, `anthropic`,
    `deepmind`, `google research`, `meta ai`, `nvidia`, `mistral`, `stability`,
    `hugging face`, `xai`, `microsoft`.
  - **+8** if it contains any of: `techcrunch`, `the verge`, `venturebeat`,
    `ars technica`, `mit tech review`, `engadget`.
  - **0** otherwise (Reddit/HN keep scoring via `_popularity` as today).
  - The tier list lives as a module constant `_TIER1` / `_TIER2` (frozensets of
    substrings) so a test can assert membership without string-matching the function.
- `_recency` unchanged in shape but its denominator tracks the window:
  `40.0 * (1.0 - hours / 96.0)` (was `/ 48.0`) so a 3-day-old tier-1 launch still
  contributes ~27 recency + 15 tier ≈ 42 > 20.

Net effect on the worked example (OpenAI blog, single feed, 30 h old):
`_recency ≈ 27 + _popularity 0 + _cross_source 0 + _keyword_fit ≈ 7 + _source_spread 0
+ _source_tier 15 ≈ 49` → clears `20` comfortably, and still ranks *below* a
cross-posted breaking story (which also gets `_cross_source 20 + _source_spread ≥5`).

### 4.3 `write.write_share` — accept all AI news, emit an angle (`write.py`)

`build_share_prompt` system prompt rewrite (keep `_IMAN_VOICE` verbatim):

- Task line: *"bài nguồn nói về MỘT chuyện đáng chú ý trong giới AI — có thể là ra mắt
  sản phẩm, rò rỉ/tin đồn, phân tích, gọi vốn, kết quả nghiên cứu, benchmark, tranh
  cãi, hay chính sách."* (drop "VỪA RA MẮT" exclusivity).
- Add: *"Chọn `angle` HỢP NHẤT với tin: `tin-nong` (chuyện vừa xảy ra → 'tin này dạy
  mình gì'), `quan-diem` (phản biện cách hiểu số đông), `xu-huong` (tin này nằm trong
  một cú dịch chuyển lớn hơn), `chuyen-thuc-chien` (rút ra cách áp dụng thật, kể như
  trải nghiệm)."*
- The five-step item spine (`(a) CÁI GÌ VỪA RA → …`) becomes angle-aware guidance:
  *"Nếu `tin-nong`/`xu-huong`: (a) chuyện gì → (b) nó thực sự nghĩa là gì, dùng chi
  tiết THẬT trong bài nguồn → (c) khác gì trước đây → (d) ảnh hưởng tới bạn thế nào →
  (e) nên làm gì. Nếu `quan-diem`: nêu cách hiểu phổ biến → vì sao nó thiếu/sai → góc
  đúng hơn → hệ quả. Nếu `chuyen-thuc-chien`: bối cảnh → mình thử thế nào → vướng gì →
  bài học rút ra."*
- JSON keys become: `angle`, `caption_fb`, `caption_ig`, `hashtags`, `cover_title`,
  `slides`, `risk` (adds `angle`; everything else unchanged).
- The skip clause narrows: *"Nếu bài nguồn KHÔNG liên quan AI, hoặc không có đủ dữ kiện
  cụ thể để viết, trả về `{\"skip\": true, \"reason\": \"...\"}`."* — **not** "isn't a
  launch".

`write_share` (the function): after `_validate_share`, also read and validate
`data["angle"]` ∈ `ANGLES` (raise `WriteError(f"angle không hợp lệ: {angle!r}")`), and
return it. Its return type gains `angle`:

- `write_share` currently returns an `ArticleContent`. `ArticleContent` gains an
  `angle: str` field (default `""` for back-compat with any existing constructor call).
  `write_take` (below) sets it too.

### 4.4 Fallback: `config/topics.yaml` + `topics.propose_topic` + `write.write_take`

`config/topics.yaml` — replace the whole file:

```yaml
# Ngân hàng chủ đề fall-back — CHỈ dùng khi không có tin AI nào đáng viết.
# Giọng: sắc, có chính kiến (xem _IMAN_VOICE). KHÔNG listicle "top công cụ".

# angle = quan-diem
takes:
  - "Đa số người học prompt sai chỗ — thứ thực sự quyết định kết quả"
  - "Đừng vội thay người bằng AI: việc AI vẫn làm tệ hơn bạn"
  - "'Người biết AI sẽ thay người không biết' — câu này đang bỏ sót điều gì"
  - "Học thêm 10 công cụ AI nữa không làm bạn giỏi hơn"
  - "Vì sao 'AI viết giúp' đang làm nhiều người viết dở đi"
  - "Miễn phí không phải lý do để dùng một công cụ AI"
  - "Bạn không cần 'prompt hoàn hảo', bạn cần biết mình muốn gì"
  - "AI làm được 80% việc — và vì sao 20% còn lại mới là nghề của bạn"
  - "Tự động hoá sai việc còn tệ hơn làm tay"
  - "Đo lường sai: vì sao 'tiết kiệm thời gian' không phải thước đo tốt"
  - "Chạy theo mọi model mới là cách chắc chắn không đi tới đâu"
  - "Kỹ năng dùng AI đáng giá nhất không nằm ở phần mềm nào cả"

# angle = xu-huong
shifts:
  - "Cú dịch chuyển từ 'chatbot trả lời' sang 'agent tự làm' — nghĩa là gì với bạn"
  - "Vì sao 12 tháng tới nghề dựng nội dung sẽ tách làm hai nhóm"
  - "Giá token rớt hàng trăm lần — điều đó mở ra cái gì"
  - "Khi ai cũng có cùng công cụ AI, thứ gì trở nên đắt giá"
  - "Nội dung AI tạo tràn lan — người xem sẽ trả tiền cho cái gì"
  - "Từ 'biết code' sang 'biết mô tả điều mình muốn' — nghề lập trình đang đổi"
  - "Vì sao các đội nhỏ giờ làm được việc trước đây cần cả công ty"
  - "AI cá nhân hoá tới mức nào thì thói quen mua hàng thay đổi"
  - "Lớp công việc mới xuất hiện quanh việc 'kiểm định đầu ra của AI'"
  - "Khoảng cách không còn là 'có AI hay không' mà là 'dùng vào đâu'"

recent_window_days: 45
```

`topics.propose_topic` — the prompt now: *"Chọn ĐÚNG MỘT mục từ `takes` hoặc `shifts`
(hoặc tự nghĩ một câu cùng tinh thần), KHÔNG trùng 'đã đăng gần đây'. Trả JSON
`{\"topic\": <=16 từ, \"angle\": \"quan-diem\" nếu lấy từ takes / \"xu-huong\" nếu từ
shifts, \"why\": một câu góc nhìn}"*. `propose_topic` returns a dict
`{"topic": str, "angle": str, "why": str}` with `angle ∈ {quan-diem, xu-huong}`; on a
missing/invalid `angle` it defaults to `quan-diem` and logs a warning.

`write.write_take(topic, angle, why, voice, generate)` — **replaces** `write_topic_post`
(rename; delete `write_topic_post`, `build_topic_prompt`, and any listicle-only
validator such as a `_validate_topic`):

- System prompt = the channel identity line + `_ARTICLE_GUARDRAILS` + `_IMAN_VOICE` +
  the `_STORYBOARD_SPEC` (§4.5 relaxed form) + *"Đây là bài `{angle}` — KHÔNG có bài
  nguồn, viết từ hiểu biết chung. KHÔNG bịa số liệu cụ thể; nếu cần ví dụ, dùng ví dụ
  chung/định tính. `hook.tools = []` (bài này không xoay quanh một sản phẩm)."*
- User prompt: `CHỦ ĐỀ: {topic}` / `GÓC: {angle}` / `Ý: {why}`.
- Same JSON contract as `write_share` minus `angle` from the model (the caller already
  knows it): `caption_fb`, `caption_ig`, `hashtags`, `cover_title`, `slides`, `risk`.
- Returns an `ArticleContent` with `angle` set from the argument.
- Keeps the existing 2-attempt `_SHAPE_NUDGE` retry loop.

### 4.5 `article_run.draft` wiring (`src/pipeline/article_run.py`)

- News branch: `article = write.write_share(...)` → on success `angle = article.angle`
  (was hard-coded `""`).
- Fallback branch: `spec = topics.propose_topic(...)`;
  `article = write.write_take(spec["topic"], spec["angle"], spec.get("why",""), voice,
  generate=generate)`; `angle = spec["angle"]`.
- **Same-day variety:** the sibling slot's `angle` is already reachable via
  `other = ds.get_safe(date, _OTHER[slot])`. Pass `other.get("angle")` into both
  `write_share` (as a system-prompt line: *"Slot kia hôm nay đã dùng góc `{x}` — nếu
  hợp lý, chọn góc khác cho đa dạng."*) and `topics.propose_topic` (bias `takes` vs
  `shifts` away from the sibling's angle). Best-effort — not a hard constraint (a
  genuinely better angle wins).
- `ds.put(..., angle=angle)` already happens; no change there.
- `marker = "📰" if is_news else "💡"` unchanged.

### 4.6 Storyboard spec relaxation (`write.py` `_STORYBOARD_SPEC`)

The current text makes product/domain/logo the default and treats a productless
slide as an edge case. Reword so opinion/trend pieces are first-class:

- Keep the hard rule: *when a slide names a REAL product, `tool`/`domain` are
  mandatory and must be the genuine official domain — never invent one.*
- Change the framing: *"Nhiều bài (quan-diem / xu-huong / tin-nong không xoay quanh
  một sản phẩm) sẽ có `hook.tools = []` và mọi `item.tool = null` — đó là BÌNH THƯỜNG,
  không phải thiếu sót."*
- `item.body` guidance: *"40-70 từ, CỤ THỂ — 'cụ thể' nghĩa là có ví dụ / con số / bước
  làm THẬT, HOẶC một lập luận sắc có dẫn chứng. Không một dòng cụt, không nói chung
  chung."*

## 5. Files touched

| File | Change |
|---|---|
| `src/pipeline/collect.py` | `MAX_AGE_HOURS` 48→96; `ARTICLE_DEBUG` per-feed logging |
| `src/pipeline/score.py` | `_source_tier` + `_TIER1`/`_TIER2`; `_recency` denom 48→96; `ARTICLE_DEBUG` per-candidate logging |
| `src/pipeline/write.py` | `ANGLES`; `build_share_prompt` rewrite; `write_share` returns angle; `write_take` replaces `write_topic_post`; `build_topic_prompt` removed; `_STORYBOARD_SPEC` reworded |
| `src/pipeline/topics.py` | `propose_topic` prompt + return `{topic, angle, why}` |
| `src/pipeline/models.py` | `ArticleContent.angle: str = ""` |
| `src/pipeline/article_run.py` | news angle from `write_share`; `write_take` call; sibling-angle hint |
| `config/settings.yaml` | `articles.min_score` 45→20 |
| `config/topics.yaml` | replaced: `takes` + `shifts` |
| `tests/test_score.py`, `tests/test_write.py`, `tests/test_topics.py`, `tests/test_article_run.py` | per §6 |

## 6. Testing

- **`tests/test_score.py`**
  - a single-source tier-1 RSS candidate (`source="rss:OpenAI Blog"`), 30 h old, no
    reddit hint → `score_candidate` ≥ 20 and `pick_n` returns it.
  - `_source_tier`: `"rss:OpenAI Blog"` → 15; `"rss:TechCrunch AI"` → 8;
    `"reddit:r/artificial"` → 0.
  - `MAX_AGE_HOURS`: `collect`-level — an entry 80 h old is kept, 100 h old is dropped
    (fixture feed with `_fresh`).
  - the ordering invariant still holds: a cross-posted breaking story (2 similar
    titles, both < 6 h) outranks the single-source tier-1 item.
- **`tests/test_write.py`**
  - `write_share` on a fake *analysis* source (title "Phân tích: vì sao mô hình mở
    đang bắt kịp", body ≥ 400 chars, no "ra mắt") → returns `ArticleContent` with
    `angle ∈ ANGLES`, `caption_fb` non-empty, `slides` valid; a fake LLM returning
    `angle: "xu-huong"` is accepted, `angle: "linh-tinh"` raises `WriteError`.
  - `write_share` skip: fake source about cooking → `{"skip": true}` path →
    `_Decline` raised (unchanged mechanism).
  - `write_take("Đa số người học prompt sai chỗ", "quan-diem", "…", voice, fake)` →
    `ArticleContent(angle="quan-diem")`, `slides` valid with `hook.tools == []` and
    every `item.tool is None` accepted (not a WriteError).
  - `write_topic_post` / `build_topic_prompt` no longer importable (removed).
- **`tests/test_topics.py`**
  - `propose_topic` with a fake LLM returning `{"topic": "...", "angle": "xu-huong",
    "why": "..."}` → passes through; `{"angle": "bogus"}` → defaults to `quan-diem`
    + warning; a topic equal to a `recent` title is rejected by the prompt (assert the
    prompt text contains the recent block — mechanism unchanged).
- **`tests/test_article_run.py`**
  - news-first: `collect.collect` monkeypatched to yield one tier-1 candidate that
    clears the new gate; `write_share` fake → the drafted slot has non-empty
    `sources`, `angle` == the fake's angle, `format == "share"`.
  - fallback: `collect.collect` yields nothing → `propose_topic` + `write_take` fakes
    → slot `sources == []`, `angle ∈ {quan-diem, xu-huong}`.
  - sibling variety: seed the morning slot with `angle: "tin-nong"`; run evening with
    a fake `write_share` that echoes the sibling-angle hint it received → assert the
    hint string ("Slot kia hôm nay đã dùng góc tin-nong") reached the prompt.
  - `python -m pipeline.article_run --slot morning --root <tmp> --fake-llm` smoke
    (both the news and fallback fakes produce a valid storyboard) stays green.
- Full suite: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q` and
  `… tests/video -q` green (video tests unaffected — `script.generate_from_article`
  consumes `caption_fb` + `angle` string, both still present).

## 7. Build order (→ plan)

1. **Diagnostic** — `ARTICLE_DEBUG` logging in `collect` + `score`; run once with
   network; report the real feed/score numbers. Gate: numbers confirm §1.
2. **Scoring gate** — `min_score`, `MAX_AGE_HOURS`, `_source_tier`, `_recency` denom +
   `test_score.py`.
3. **`ANGLES` + `write_share`** — prompt rewrite, return angle, `ArticleContent.angle`,
   `_STORYBOARD_SPEC` reword + `test_write.py` (share half).
4. **Fallback** — `topics.yaml` replace, `propose_topic`, `write_take` (replace
   `write_topic_post`) + `test_topics.py` + `test_write.py` (take half).
5. **`article_run` wiring** — news angle, `write_take` call, sibling-angle hint +
   `test_article_run.py` + full suite green.

## 8. Out of scope

- LLM web search / any paid news API.
- Recycling stale news for the fallback.
- The legacy `write_post` / `build_prompt` / `ALLOWED_ANGLES` (not on the draft path).
- Video pipeline, `styles`, `images`, `publish`.
- Tuning the exact tier lists / score constants beyond what the diagnostic (task 1)
  shows is needed — a follow-up can adjust once real runs accumulate.
