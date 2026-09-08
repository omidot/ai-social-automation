from __future__ import annotations
import json
import re
from pathlib import Path

from ..llm import generate as _default_generate, parse_json_response, LLMError
from ..models import Candidate, PostContent
from . import VideoScriptError
from .models import Script

_NUDGE = 15  # allow spoken/pacing slack around the displayed-word band


def build_prompt(cand: Candidate, post: PostContent, voice: dict, cfg: dict,
                 *, with_meta: bool = False) -> tuple[str, str]:
    wmin, wmax = cfg["words_min"], cfg["words_max"]
    shape = ("{sections:[{label,card_start}], "
             "cards:[{lines,variant,anchor,motion_in,motion_out,num?}]"
             + (", publish:{title,description,hashtags,keywords,tiktok_caption}}"
                if with_meta else "}"))
    system = (
        f"Bạn viết kịch bản video dọc ~{cfg['target_seconds']} giây cho kênh "
        f"\"{voice.get('ten_kenh', '')}\" về AI, phong cách kinetic typography. "
        f"Giọng: {voice.get('giong', '')}. Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Góc bài: {post.angle}. Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. "
        f"CHỈ trả về một object JSON: {shape}. "
        f"Tổng số TỪ HIỂN THỊ trên màn hình từ {wmin} đến {wmax} (không tính dòng bắt đầu bằng '~'). "
        "12-18 card; 3-5 section; sections[0].card_start=0; card_start tăng dần. "
        "Card 0 là HOOK (0-3s). Card cuối là câu chốt mạnh. Mỗi 'line' <= 7 từ. "
        "Thêm line '~cái' hoặc '~thì' khi cần nhịp đọc (được đọc, không hiện). "
        "variant ∈ stack|right|hero|invert|mark|stair|numeral|strike; "
        "anchor ∈ top|mid|low; motion_in ∈ rise|fall|slideR|slideL|wipe|pop|slam; "
        "motion_out ∈ up|down|dissolve|shrink|wipeOut. "
        "Hai card liền nhau KHÔNG cùng motion_in. Số liệu THẬT thì đặt riêng một card và set 'num'. "
        "Không bịa số. Toàn bộ tiếng Việt."
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
    if not (8 <= len(cards) <= 20):
        raise VideoScriptError(f"card count {len(cards)} out of 8..20")
    if not (2 <= len(sections) <= 6):
        raise VideoScriptError(f"section count {len(sections)} out of 2..6")
    try:
        s = Script.from_dict(data)
    except (KeyError, TypeError) as e:
        raise VideoScriptError(f"bad card/section fields: {e}") from e
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
        wc = s.word_count
        if wmin - _NUDGE <= wc <= wmax + _NUDGE:
            return s
        if attempt == 2:
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
        wc = s.word_count
        if wmin - _NUDGE <= wc <= wmax + _NUDGE:
            return s, meta
        if attempt == 2:
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
