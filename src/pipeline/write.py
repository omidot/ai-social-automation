from __future__ import annotations

import re

from .llm import generate as _default_generate, parse_json_response, LLMError
from .models import Candidate, PostContent


class WriteError(Exception):
    pass


_URL_RE = re.compile(r"https?://\S+")


def _strip_urls(text: str) -> str:
    """Remove any http(s) URL tokens from human-visible caption text and tidy
    the artefacts a removed link leaves behind (dangling ' — ', empty
    'Nguồn:' lines, empty brackets, doubled spaces/blank lines)."""
    if not text:
        return text
    out = _URL_RE.sub("", text)
    out = re.sub(r"\(\s*\)", "", out)                      # empty () left by a link
    out = re.sub(r"\[\s*\]", "", out)                      # empty []
    out = re.sub(r"[ \t]*[—–-]\s*(?=\n|$)", "", out)       # dangling ' — ' at line end
    out = re.sub(r"(?m)^[ \t]*Nguồn:[ \t]*$", "", out)     # empty 'Nguồn:' line
    out = re.sub(r"Nguồn:(?:[ \t]*,)+", "Nguồn:", out)     # 'Nguồn: , ' artefact
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


ALLOWED_ANGLES = {"tin-tuc", "ung-dung-mmo", "phan-tich", "giat-gan"}
_REQUIRED = ("angle", "caption_fb", "caption_ig", "hashtags", "thumbnail_prompt",
             "thumbnail_title", "youtube_title", "youtube_desc", "tiktok_caption")


def build_prompt(cand: Candidate, voice: dict) -> tuple[str, str]:
    system = (
        f"Bạn là biên tập viên nội dung tiếng Việt cho kênh \"{voice.get('ten_kenh', '')}\" "
        f"chuyên về AI. Giọng: {voice.get('giong', '')}. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", gọi khán giả "
        f"\"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. "
        "Tự chọn 'angle' phù hợp nhất với tin trong: "
        "tin-tuc (cập nhật nhanh), ung-dung-mmo (dùng để làm gì / kiếm tiền), "
        "phan-tich (góc nhìn, tác động), giat-gan (tiêu đề mạnh, cảm xúc). "
        "CHỈ trả về một object JSON hợp lệ với đúng các khoá: "
        "angle, caption_fb, caption_ig, hashtags (mảng 8-15 chuỗi bắt đầu bằng #), "
        "thumbnail_prompt (tiếng Anh, mô tả HÌNH ẢNH, KHÔNG chứa chữ), "
        "thumbnail_title (4-10 từ tiếng Việt IN HOA), youtube_title, youtube_desc, "
        "tiktok_caption. "
        "caption_fb 150-400 từ, có xuống dòng, kết bằng một CTA. "
        "Không bịa số liệu. Toàn bộ tiếng Việt trừ thumbnail_prompt."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = (
        f"TIÊU ĐỀ GỐC: {cand.title}\n"
        f"NGUỒN: {cand.source}\n"
        f"URL: {cand.url}\n\n"
        f"NỘI DUNG BÀI GỐC:\n{article}\n"
    )
    return system, user


def _source_name(cand: Candidate) -> str:
    return cand.source.split(":", 1)[1] if ":" in cand.source else cand.source


def write_post(cand: Candidate, voice: dict, generate=_default_generate) -> PostContent:
    try:
        raw = generate(*build_prompt(cand, voice), provider="auto")
        data = parse_json_response(raw)
    except LLMError as e:
        raise WriteError(f"LLM failed: {e}") from e

    missing = [k for k in _REQUIRED if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"LLM response missing keys: {missing}")
    if data["angle"] not in ALLOWED_ANGLES:
        raise WriteError(f"invalid angle: {data['angle']!r}")
    if not isinstance(data["hashtags"], list):
        raise WriteError("hashtags must be a list")

    src_name = _source_name(cand)
    src_line = f"Nguồn: {src_name} — {cand.url}"
    caption_fb = data["caption_fb"].rstrip()
    if src_line not in caption_fb:
        caption_fb = f"{caption_fb}\n\n{src_line}"

    return PostContent(
        angle=data["angle"], caption_fb=caption_fb, caption_ig=data["caption_ig"].strip(),
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        thumbnail_prompt=data["thumbnail_prompt"].strip(),
        thumbnail_title=data["thumbnail_title"].strip(),
        youtube_title=data["youtube_title"].strip(), youtube_desc=data["youtube_desc"].strip(),
        tiktok_caption=data["tiktok_caption"].strip(),
        source_url=cand.url, source_name=src_name,
    )


def decide_format(scored, margin):
    if len(scored) <= 1:
        return "deep"
    return "deep" if (scored[0][0] - scored[1][0]) >= margin else "roundup"


_ARTICLE_GUARDRAILS = (
    "Không xuyên tạc lịch sử, không bịa số liệu, không nội dung vi phạm pháp luật, "
    "phỉ báng, hay chính trị nhạy cảm. Nếu bài chạm vùng nhạy cảm, đặt \"risk\": true."
)
_DEEP_KEYS = ("caption_fb", "caption_ig", "hashtags", "cover_title", "slides")

# Iman-Gadzhi-style voice, described in Vietnamese. Shared by both article prompts.
_IMAN_VOICE = (
    "GIỌNG VĂN (bắt buộc): Câu ngắn, dứt khoát. Nhịp mạnh. Ít từ thừa, cắt sạch chữ đệm. "
    "Có chính kiến rõ: dám nói \"đa số mọi người hiểu sai chỗ này\", "
    "\"cái thực sự quan trọng là...\". "
    "Mỗi ý là MỘT bài học hoặc nguyên tắc rút ra, KHÔNG phải tóm tắt tin — "
    "kiểu \"đây là điều tin này dạy mình:\". "
    "Nói thẳng với người đọc: \"bạn\", \"nếu bạn đang làm X thì...\". "
    "Xưng \"mình\", tự tin, không PR sáo rỗng, không hàn lâm; có thể hơi khiêu khích nhẹ. "
    "Mở đầu bằng MỘT câu tuyên bố mạnh hoặc một sự thật ngược đời — "
    "KHÔNG mở bằng \"Công ty X vừa công bố...\". "
    "Kết bằng một câu chốt sắc + một câu hỏi mời tranh luận. "
    "TUYỆT ĐỐI KHÔNG chèn URL/đường link. Chỉ nhắc tên nguồn dạng chữ (vd: \"theo VnExpress\")."
)


def build_deep_prompt(cand, voice):
    system = (
        f"Bạn là người viết tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        f"{_IMAN_VOICE} "
        "Viết bài CHUYÊN SÂU rút ra từ MỘT tin. KHÔNG phải bản tin. "
        "Mỗi đoạn = một bài học/nguyên tắc, nói rõ nó thay đổi cái gì với người đọc. "
        "CHỈ trả về JSON với khoá: "
        "caption_fb (200-350 từ, xuống dòng, kết bằng câu chốt sắc + câu hỏi tranh luận), "
        "caption_ig (<=60 từ), hashtags (8-15 chuỗi #), "
        "cover_title (4-10 từ tiếng Việt, mạnh, không PR), "
        "slides (MẢNG 2-3 thẻ, mỗi thẻ là object {\"headline\": <=8 từ tiếng Việt, "
        "\"sub\": <=16 từ, là bài học/ý chốt của thẻ đó}), risk (bool)."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = f"TIÊU ĐỀ: {cand.title}\nNGUỒN: {cand.source}\nURL: {cand.url}\n\n{article}\n"
    return system, user


def _clean_slides(raw) -> list[dict]:
    """Coerce the LLM's `slides` payload into [{"headline": str, "sub": str}, ...],
    dropping any entry without a headline."""
    out: list[dict] = []
    for s in raw or []:
        if not isinstance(s, dict):
            continue
        headline = str(s.get("headline", "")).strip()
        sub = str(s.get("sub", "")).strip()
        if headline:
            out.append({"headline": headline, "sub": sub})
    return out


def write_deep(cand, voice, generate=_default_generate):
    try:
        data = parse_json_response(generate(*build_deep_prompt(cand, voice), provider="auto"))
    except LLMError as e:
        raise WriteError(f"LLM failed: {e}") from e
    missing = [k for k in _DEEP_KEYS if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"deep response missing keys: {missing}")
    name = _source_name(cand)
    line = f"Nguồn: {name}"
    cap = _strip_urls(data["caption_fb"])
    if line not in cap:
        cap = f"{cap}\n\n{line}"
    cap_ig = _strip_urls(data["caption_ig"])
    slides = _clean_slides(data["slides"])[:3]
    if len(slides) < 2:
        raise WriteError(f"deep slides too few: {len(slides)}")
    from .models import ArticleContent
    return ArticleContent(
        format="deep", caption_fb=cap, caption_ig=cap_ig,
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        cover_title=data["cover_title"].strip().upper(),
        cover_brief=str(data.get("cover_brief", "")).strip(), slides=slides,
        sources=[{"name": name, "url": cand.url}], risk=bool(data.get("risk", False)))


def build_roundup_prompt(cands, voice):
    items = "\n\n".join(
        f"[{i+1}] {c.title}\nNGUỒN: {_source_name(c)} (tham khảo, ĐỪNG chép link: {c.url})\n"
        f"{(c.full_text or c.summary or '')[:1500]}"
        for i, c in enumerate(cands))
    system = (
        f"Bạn là người viết tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". {_ARTICLE_GUARDRAILS} "
        f"{_IMAN_VOICE} "
        f"Viết bài GOM {len(cands)} tin, đánh số 1..{len(cands)}. "
        "KHÔNG phải danh sách tin rời rạc — mỗi mục rút ra MỘT bài học hoặc ý "
        "\"cái thực sự quan trọng là...\", 2-4 câu, chỉ nhắc tên nguồn dạng chữ. "
        "Có thể có 1 câu dẫn mạnh ở đầu nối các mục lại. "
        "CHỈ trả về JSON với khoá: caption_fb (đánh số, kết bằng câu chốt sắc + "
        "câu hỏi tranh luận), caption_ig (<=40 từ), hashtags (8-15 chuỗi #), "
        "cover_title (4-10 từ tiếng Việt, mạnh), "
        f"slides (MẢNG ĐÚNG {len(cands)} thẻ, thứ tự khớp tin 1..{len(cands)}, mỗi thẻ "
        "là object {\"headline\": tiêu đề ngắn đanh <=8 từ, "
        "\"sub\": câu \"so what\" một dòng <=16 từ}), risk (bool)."
    )
    return system, f"CÁC TIN:\n\n{items}\n"


def write_roundup(cands, voice, generate=_default_generate):
    try:
        data = parse_json_response(generate(*build_roundup_prompt(cands, voice), provider="auto"))
    except LLMError as e:
        raise WriteError(f"LLM failed: {e}") from e
    missing = [k for k in _DEEP_KEYS if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"roundup response missing keys: {missing}")
    slides = _clean_slides(data["slides"])
    if len(slides) != len(cands):
        raise WriteError(f"roundup slides {len(slides)} != items {len(cands)}")
    from .models import ArticleContent
    return ArticleContent(
        format="roundup", caption_fb=_strip_urls(data["caption_fb"]),
        caption_ig=_strip_urls(data["caption_ig"]),
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        cover_title=data["cover_title"].strip().upper(),
        cover_brief=str(data.get("cover_brief", "")).strip(), slides=slides,
        sources=[{"name": _source_name(c), "url": c.url} for c in cands],
        risk=bool(data.get("risk", False)))
