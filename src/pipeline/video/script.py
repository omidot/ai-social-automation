from __future__ import annotations
import json
from pathlib import Path

from ..llm import generate as _default_generate, parse_json_response, LLMError
from ..models import Candidate, PostContent
from . import VideoScriptError
from .models import Script

_NUDGE = 15  # allow spoken/pacing slack around the displayed-word band


def build_prompt(cand: Candidate, post: PostContent, voice: dict, cfg: dict) -> tuple[str, str]:
    wmin, wmax = cfg["words_min"], cfg["words_max"]
    system = (
        f"Bạn viết kịch bản video dọc ~{cfg['target_seconds']} giây cho kênh "
        f"\"{voice.get('ten_kenh', '')}\" về AI, phong cách kinetic typography. "
        f"Giọng: {voice.get('giong', '')}. Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Góc bài: {post.angle}. Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. "
        "CHỈ trả về một object JSON: "
        "{sections:[{label,card_start}], cards:[{lines,variant,anchor,motion_in,motion_out,num?}]}. "
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


def write_script_json(s: Script, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "script.json"
    p.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
