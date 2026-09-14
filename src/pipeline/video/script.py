from __future__ import annotations
import json
import logging
import math
import re
from pathlib import Path

from ..llm import generate as _default_generate, parse_json_response, LLMError
from ..models import Candidate, PostContent
from ..write import _IMAN_VOICE
from . import VideoScriptError
from .models import Script

# Slack around the displayed-word band. Sized against the 150s target: a
# fixed 15 words made sense for a 60s script but is punishing on a band
# four times wider -- a real draft was thrown away for overshooting by 4.
log = logging.getLogger("video.script")

_NUDGE = 40
# Past the nudge the script is off-length but still perfectly renderable.
# Discarding it loses the whole draft -- and the user's turn -- over pacing,
# so the final attempt keeps it as long as the length is not absurd.
_SALVAGE_LO, _SALVAGE_HI = 0.6, 1.6


def build_prompt(cand: Candidate, post: PostContent, voice: dict, cfg: dict,
                 *, with_meta: bool = False) -> tuple[str, str]:
    wmin, wmax = cfg["words_min"], cfg["words_max"]
    shape = ("{sections:[{label,card_start}], "
             "cards:[{lines,variant,anchor,motion_in,motion_out,num?,chart?,screenshot?}]"
             + (", publish:{title,description,hashtags,keywords,tiktok_caption}}"
                if with_meta else "}"))
    system = (
        f"Bạn viết kịch bản video dọc ~{cfg['target_seconds']} giây cho kênh "
        f"\"{voice.get('ten_kenh', '')}\" về AI, phong cách kinetic typography. "
        f"{_IMAN_VOICE} "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Góc bài: {post.angle}. Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. "
        f"CHỈ trả về một object JSON: {shape}. "
        f"Tổng số TỪ HIỂN THỊ trên màn hình từ {wmin} đến {wmax} (không tính dòng bắt đầu bằng '~'). "
        "28-40 card; 5-7 section; sections[0].card_start=0; card_start tăng dần. "
        "Mỗi 'line' <= 7 từ. "
        "\n\nGIỮ CHÂN NGƯỜI XEM — đây là yêu cầu quan trọng nhất, quan trọng hơn "
        "đưa tin đầy đủ. Video bị lướt qua là video vứt đi. Bắt buộc:\n"
        "1. HOOK (card 0-1, 3 giây đầu): mở bằng CON SỐ hoặc sự kiện gây sốc cụ thể, "
        "không mở bằng câu dẫn chung chung. SAI: 'AI đang thay đổi thế giới'. "
        "ĐÚNG: 'Một con AI vừa làm xong việc 90 năm của nhà toán học trong 3 ngày'.\n"
        "2. VÒNG LẶP MỞ: ngay trong 10 giây đầu phải hứa một điều chỉ tiết lộ ở cuối "
        "(vd 'thứ kỳ lạ nhất nằm ở dòng cuối cùng'), rồi PHẢI trả lời đúng lời hứa đó "
        "ở card gần cuối. Không hứa rồi bỏ lửng.\n"
        "3. TRẢ THƯỞNG LIÊN TỤC: cứ khoảng 4-6 card phải có một điểm bất ngờ mới — con "
        "số lệch hẳn dự đoán, một so sánh đắt, hoặc một sự thật ngược đời. Không để "
        "người xem đi quá 15 giây mà không nhận được gì mới.\n"
        "4. CỤ THỂ, KHÔNG CHUNG CHUNG: mọi câu phải có tên riêng, con số, mốc thời gian "
        "hoặc hệ quả đo được. Cấm những câu ai viết cũng được như 'công nghệ phát triển "
        "nhanh', 'điều này rất quan trọng', 'tương lai sẽ khác'.\n"
        "5. ĐỔI NHỊP: xen câu rất ngắn (2-3 từ) giữa các câu dài để phá đều đều. Dùng "
        "câu hỏi trực diện với người xem ở giữa bài, không dồn hết xuống cuối.\n"
        "6. CHỐT ĐỂ XEM LẠI: card cuối phải gọi lại chi tiết đã nêu ở hook, khiến người "
        "xem muốn tua lại đầu để kiểm chứng. Kết bằng câu hỏi buộc phải chọn phe "
        "(vd 'bạn chọn tốc độ hay chính xác?'), không phải câu hỏi mơ hồ.\n\n"
        "variant ∈ stack|right|hero|invert|mark|stair|numeral|strike; "
        "anchor ∈ top|mid|low; motion_in ∈ rise|fall|slideR|slideL|wipe|pop|slam; "
        "motion_out ∈ up|down|dissolve|shrink|wipeOut. "
        "Hai card liền nhau KHÔNG cùng motion_in. Số liệu THẬT thì đặt riêng một card và set 'num'. "
        "'num' PHẢI là số thuần (vd 50, 2.5), TUYỆT ĐỐI không kèm đơn vị/ký hiệu (không viết "
        "'50 USD' hay '2.5x') — đơn vị/ký hiệu đó viết trong 'lines' của card, không phải "
        "trong 'num'. Không bịa số. Toàn bộ tiếng Việt. "
        "BẮT BUỘC giữ nguyên tên riêng cụ thể xuất hiện trong TIÊU ĐỀ/TÓM TẮT (tên người, "
        "tên công ty/sản phẩm) — card HOOK phải nêu rõ ai/hãng nào vừa làm gì, TUYỆT ĐỐI "
        "không thay bằng đại từ mơ hồ như 'họ', 'các trùm AI', 'ông lớn' khi danh tính cụ thể "
        "đã biết. "
        "Người xem chỉ nghe MỘT LẦN, không tua lại được: mỗi khi dùng thuật ngữ trừu tượng "
        "hoặc tên tổ chức lạ (vd 'thâu tóm quy định', 'METR'), câu ngay sau đó PHẢI giải "
        "thích bằng lời thật đơn giản, không cần biết trước mới hiểu. Tránh xâu chuỗi liên "
        "tiếp nhiều lập luận trừu tượng mà không xen ví dụ/hệ quả cụ thể. 2-3 card gần cuối "
        "phải nói thẳng điều này ảnh hưởng gì tới người xem (vd: người làm sản phẩm AI, "
        "người dùng công nghệ) thay vì chỉ chốt bằng câu hỏi mơ hồ. "
        "Một card có thể thêm 'chart' HOẶC 'screenshot' (không dùng chung với nhau hay với "
        "'num', tối đa một trong ba trên mỗi card, và cả hai đều KHÔNG bắt buộc): "
        "'chart': {kind:'stat'|'line'|'bar'|'hbar', items:[...], unit?} — "
        "kind='stat' là khối số liệu (nhãn trái, số to bên phải), cần 2-4 items dạng "
        "{label,value}; dùng cho thông số rời rạc như giá, dung lượng, tốc độ. "
        "kind='bar' cần ĐÚNG 2 items {label,value} để so kè hai bên; 'hbar' cần 2-4 items "
        "{label,value}; 'line' cần >=3 items dạng {value} cho xu hướng theo thời gian. "
        "kind='gauge' là thanh đo có mũi tên, ĐÚNG 2 items {label,value}: item đầu là điểm "
        "đạt được, item sau là mốc tối đa (vd điểm 98.6 trên thang 100). "
        "kind='chips' là các thẻ tên nằm cạnh nhau, 2-4 items dạng {label} (KHÔNG cần value) "
        "— dùng khi bài kể tên vài sản phẩm/tính năng mới cùng lúc. "
        "'screenshot': {query} — chỉ thêm khi bài nhắc tới một sản phẩm/repo/trang web CỤ THỂ "
        "có thể tìm bằng Google (vd query='GitHub OpenAI Codex'), query tối đa 100 ký tự. "
        "QUAN TRỌNG: video toàn chữ rất chán. Hễ card nào có từ 2 con số trở lên đáng so "
        "sánh thì PHẢI gắn 'chart'. Nhắm ít nhất 3-4 card có chart hoặc screenshot trong "
        "mỗi kịch bản; chỉ bỏ qua khi bài thật sự không có số liệu hay sản phẩm cụ thể nào."
    )
    if with_meta:
        system += (
            " Khối 'publish': title <=70 ký tự, giật tít, có yếu tố tò mò hoặc con số. "
            "description 2-4 câu + 1 lời kêu gọi theo dõi kênh, KHÔNG chèn URL. "
            "hashtags 8-12, mỗi cái bắt đầu '#', không dấu cách. "
            "keywords 5-10 từ khoá cho YouTube (không '#'). "
            "tiktok_caption <=150 ký tự kèm 3-5 hashtag inline. Tất cả tiếng Việt."
        )
    article = (cand.full_text or cand.summary or cand.title)[:5000]
    user = (
        f"TIÊU ĐỀ: {cand.title}\nNGUỒN: {cand.source}\nURL: {cand.url}\n\n"
        f"TÓM TẮT/BÀI GỐC:\n{article}\n\n"
        f"CAPTION FACEBOOK (tham khảo giọng, đừng chép):\n{post.caption_fb}\n"
    )
    return system, user


def _validate(data: dict, cfg: dict) -> Script:
    if not isinstance(data, dict) or "cards" not in data or "sections" not in data:
        raise VideoScriptError("missing 'cards'/'sections'")
    cards, sections = data["cards"], data["sections"]
    if not (18 <= len(cards) <= 48):
        raise VideoScriptError(f"card count {len(cards)} out of 18..48")
    if not (2 <= len(sections) <= 6):
        raise VideoScriptError(f"section count {len(sections)} out of 2..6")
    try:
        s = Script.from_dict(data)
    except (KeyError, TypeError) as e:
        raise VideoScriptError(f"bad card/section fields: {e}") from e
    _CHART_ITEM_BOUNDS = {"line": (3, None), "bar": (2, 2), "hbar": (2, 4), "stat": (2, 4),
                          "gauge": (2, 2), "chips": (2, 4)}
    # chips chỉ là các nhãn tên -- ép tác giả bịa ra một con số cho chúng là vô nghĩa
    _NO_VALUE_KINDS = {"chips"}
    for i, c in enumerate(s.cards):
        set_fields = [name for name, val in (("num", c.num), ("chart", c.chart),
                                             ("screenshot", c.screenshot)) if val is not None]
        if len(set_fields) > 1:
            raise VideoScriptError(f"card {i}: chỉ được set 1 trong num/chart/screenshot, có {set_fields}")
        if c.chart is not None:
            if c.chart.kind not in _CHART_ITEM_BOUNDS:
                raise VideoScriptError(f"card {i}: chart.kind {c.chart.kind!r} không hợp lệ")
            lo, hi = _CHART_ITEM_BOUNDS[c.chart.kind]
            n_items = len(c.chart.items)
            if n_items < lo or (hi is not None and n_items > hi):
                raise VideoScriptError(
                    f"card {i}: chart '{c.chart.kind}' có {n_items} items, cần {lo}..{hi or 'nhiều hơn'}")
            if c.chart.kind in _NO_VALUE_KINDS:
                for item in c.chart.items:
                    if not str(item.get("label") or "").strip():
                        raise VideoScriptError(f"card {i}: chart '{c.chart.kind}' item thiếu 'label': {item}")
            else:
                for item in c.chart.items:
                    v = item.get("value")
                    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                        raise VideoScriptError(f"card {i}: chart item thiếu 'value' dạng số: {item}")
        if c.screenshot is not None:
            q = c.screenshot.query
            if not isinstance(q, str) or not q.strip():
                raise VideoScriptError(f"card {i}: screenshot.query rỗng")
            if len(q) > 100:
                raise VideoScriptError(f"card {i}: screenshot.query dài {len(q)} > 100 ký tự")
    if s.sections[0].card_start != 0:
        raise VideoScriptError("sections[0].card_start must be 0")
    starts = [sec.card_start for sec in s.sections]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise VideoScriptError("section card_start not strictly increasing")
    if starts[-1] >= len(s.cards):
        raise VideoScriptError("section card_start beyond last card")
    return s


_HASHTAG = re.compile(r"^#\S+$")


def _validate_meta(data: dict) -> "VideoMeta":
    from .models import VideoMeta
    try:
        title = str(data["title"]).strip()
        desc = str(data["description"]).strip()
        tags = [str(h).strip() for h in data["hashtags"]]
        kws = [str(k).strip() for k in data["keywords"]]
        tk = str(data["tiktok_caption"]).strip()
    except (KeyError, TypeError) as e:
        raise VideoScriptError(f"bad publish meta: {e}") from e
    if not (10 <= len(title) <= 70):
        raise VideoScriptError(f"meta title length {len(title)} outside 10..70")
    if not (8 <= len(tags) <= 12) or not all(_HASHTAG.match(h) for h in tags):
        raise VideoScriptError(f"meta hashtags invalid: {tags}")
    if not (5 <= len(kws) <= 10):
        raise VideoScriptError(f"meta keywords count {len(kws)} outside 5..10")
    if len(tk) > 150:
        raise VideoScriptError(f"tiktok_caption {len(tk)} > 150 chars")
    return VideoMeta(title=title, description=desc, hashtags=tags,
                     keywords=kws, tiktok_caption=tk)


def generate(cand: Candidate, post: PostContent, voice: dict, cfg: dict, llm=None) -> Script:
    llm = llm or _default_generate
    system, user = build_prompt(cand, post, voice, cfg)
    wmin, wmax = cfg["words_min"], cfg["words_max"]

    for attempt in (1, 2):
        try:
            raw = llm(system, user, provider="auto")
            data = parse_json_response(raw)
            s = _validate(data, cfg)
        except LLMError as e:
            raise VideoScriptError(f"LLM failed: {e}") from e
        except VideoScriptError as e:
            if attempt == 2:
                raise
            user = (user + f"\n\n[SỬA] Bản vừa rồi bị lỗi: {e}. "
                    "Sửa đúng lỗi này, giữ nguyên cấu trúc JSON.")
            continue
        wc = s.word_count
        if wmin - _NUDGE <= wc <= wmax + _NUDGE:
            return s
        if attempt == 2:
            if wmin * _SALVAGE_LO <= wc <= wmax * _SALVAGE_HI:
                log.warning("word count %d outside %d-%d -- keeping the draft anyway",
                            wc, wmin, wmax)
                return s
            raise VideoScriptError(f"word count {wc} outside {wmin}-{wmax} after retry")
        user = (user + f"\n\n[SỬA] Bản vừa rồi có {wc} từ hiển thị. "
                f"Viết lại cho đủ {wmin}-{wmax} từ, giữ nguyên cấu trúc JSON.")
    raise VideoScriptError("unreachable")  # for type-checkers


def generate_from_article(title: str, source_url: str, body_text: str,
                          caption_fb: str, angle: str, voice: dict, cfg: dict,
                          llm=None) -> tuple[Script, "VideoMeta"]:
    from datetime import datetime, timezone
    cand = Candidate(url=source_url or "", title=title, source="",
                     published_at=datetime.now(timezone.utc),
                     summary="", full_text=body_text or caption_fb or title)
    post = PostContent(angle=angle, caption_fb=caption_fb, caption_ig="",
                       hashtags=[], thumbnail_prompt="", thumbnail_title="",
                       youtube_title="", youtube_desc="", tiktok_caption="",
                       source_url=source_url or "", source_name="")
    llm = llm or _default_generate
    system, user = build_prompt(cand, post, voice, cfg, with_meta=True)
    wmin, wmax = cfg["words_min"], cfg["words_max"]

    for attempt in (1, 2):
        try:
            raw = llm(system, user, provider="auto")
            data = parse_json_response(raw)
            s = _validate(data, cfg)
            meta = _validate_meta(data.get("publish", {}))
        except LLMError as e:
            raise VideoScriptError(f"LLM failed: {e}") from e
        except VideoScriptError as e:
            if attempt == 2:
                raise
            user = (user + f"\n\n[SỬA] Bản vừa rồi bị lỗi: {e}. "
                    "Sửa đúng lỗi này, giữ nguyên cấu trúc JSON kể cả 'publish'.")
            continue
        wc = s.word_count
        if wmin - _NUDGE <= wc <= wmax + _NUDGE:
            return s, meta
        if attempt == 2:
            if wmin * _SALVAGE_LO <= wc <= wmax * _SALVAGE_HI:
                log.warning("word count %d outside %d-%d -- keeping the draft anyway",
                            wc, wmin, wmax)
                return s, meta
            raise VideoScriptError(f"word count {wc} outside {wmin}-{wmax} after retry")
        user = (user + f"\n\n[SỬA] Bản vừa rồi có {wc} từ hiển thị. "
                f"Viết lại cho đủ {wmin}-{wmax} từ, giữ nguyên cấu trúc JSON kể cả 'publish'.")
    raise VideoScriptError("unreachable")  # for type-checkers


def write_script_json(s: Script, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "script.json"
    p.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
