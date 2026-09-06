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


_ARTICLE_GUARDRAILS = (
    "Không xuyên tạc lịch sử, không bịa số liệu, không nội dung vi phạm pháp luật, "
    "phỉ báng, hay chính trị nhạy cảm. Nếu bài chạm vùng nhạy cảm, đặt \"risk\": true."
)

# roles every `slides` payload must carry, in this exact order
SLIDE_ROLES = ("hook", "what", "why", "how", "close")
_SHARE_KEYS = ("caption_fb", "caption_ig", "hashtags", "cover_title", "slides")

# Iman-Gadzhi-style voice, described in Vietnamese.
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


def build_share_prompt(cand: Candidate, voice: dict) -> tuple[str, str]:
    """System + user prompt for the single-topic knowledge-share writer.

    The piece is ONE person sharing ONE thing AI can now do — not a reporter,
    not a numbered news round-up.
    """
    system = (
        f"Bạn là người viết tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        f"{_IMAN_VOICE} "
        "NHIỆM VỤ: viết về ĐÚNG MỘT thứ mà AI giờ làm được, như một người đang "
        "chia sẻ điều mình thật sự hiểu — KHÔNG phải phóng viên, KHÔNG phải một "
        "bản tin, KHÔNG viết \"tuần này có các tin...\", KHÔNG đánh số danh sách tin. "
        "Sắp mạch suy nghĩ theo 5 bước: "
        "1) HOOK — một câu tuyên bố mạnh kiểu \"AI giờ làm được X\" hoặc một sự "
        "thật khiến người đọc dừng lại. "
        "2) CỤ THỂ LÀ GÌ — AI làm được điều đó như thế nào, ví dụ thật, dễ hình dung. "
        "3) NGƯỜI ĐỌC ĐƯỢC GÌ — nó giúp BẠN việc gì: tiết kiệm thời gian/tiền, "
        "làm được thứ trước đây không làm được, thay đổi cách làm việc. "
        "4) CÁCH BẮT ĐẦU — bạn tự dùng thế nào, công cụ nào, bước đầu tiên. "
        "5) CHỐT — một câu đọng lại + một câu hỏi mời bình luận. "
        "caption_fb: 180-320 từ, VIẾT THÀNH ĐOẠN VĂN MẠCH LẠC (xuống dòng giữa các "
        "ý), TUYỆT ĐỐI KHÔNG đánh số \"1. 2. 3.\", không phải danh sách tin. Giọng "
        "dứt khoát, chia sẻ, \"mình\"/\"bạn\", có chính kiến, không PR sáo rỗng, "
        "không hàn lâm. KHÔNG chèn URL. Kết bằng một câu hỏi. "
        "caption_ig: <=50 từ, cùng tinh thần. "
        "CHỈ trả về một object JSON hợp lệ với đúng các khoá: "
        "caption_fb, caption_ig, hashtags (mảng 8-15 chuỗi bắt đầu bằng #), "
        "cover_title (<=9 từ, chính là câu hook rút gọn), "
        "slides (ĐÚNG 5 object, role lần lượt là hook, what, why, how, close theo "
        "đúng thứ tự đó; mỗi object {\"role\": <role>, \"headline\": <=8 từ, "
        "\"body\": <=22 từ — chính là chữ hiển thị trên slide bước đó}), "
        "risk (bool). Toàn bộ tiếng Việt."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = (
        f"TIÊU ĐỀ: {cand.title}\n"
        f"NGUỒN: {cand.source}\n"
        f"URL: {cand.url}\n\n"
        f"NỘI DUNG BÀI GỐC:\n{article}\n"
    )
    return system, user


def write_share(cand: Candidate, voice: dict, generate=_default_generate):
    """Turn one candidate into a single-topic knowledge-share article
    (``format="share"``) with a 5-slide hook/what/why/how/close arc."""
    try:
        data = parse_json_response(
            generate(*build_share_prompt(cand, voice), provider="auto"))
    except LLMError as e:
        raise WriteError(f"LLM failed: {e}") from e

    missing = [k for k in _SHARE_KEYS if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"share response missing keys: {missing}")
    if not isinstance(data["hashtags"], list):
        raise WriteError("hashtags must be a list")

    raw_slides = data["slides"]
    if not isinstance(raw_slides, list) or len(raw_slides) != 5:
        got = len(raw_slides) if isinstance(raw_slides, list) else type(raw_slides).__name__
        raise WriteError(f"share needs exactly 5 slides, got {got}")
    slides: list[dict] = []
    for i, s in enumerate(raw_slides):
        if not isinstance(s, dict):
            raise WriteError(f"slide {i} is not an object")
        role = str(s.get("role", "")).strip().lower()
        if role != SLIDE_ROLES[i]:
            raise WriteError(
                f"slide {i} role {role!r} != expected {SLIDE_ROLES[i]!r} "
                f"(order must be {list(SLIDE_ROLES)})")
        slides.append({
            "role": role,
            "headline": _strip_urls(str(s.get("headline", "")).strip()),
            "body": _strip_urls(str(s.get("body", "")).strip()),
        })

    name = _source_name(cand)
    line = f"Nguồn: {name}"
    cap = _strip_urls(data["caption_fb"])
    if line not in cap:
        cap = f"{cap}\n\n{line}"
    cap_ig = _strip_urls(data["caption_ig"])

    from .models import ArticleContent
    return ArticleContent(
        format="share", caption_fb=cap, caption_ig=cap_ig,
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        cover_title=str(data["cover_title"]).strip(),
        slides=slides,
        sources=[{"name": name, "url": cand.url}],
        risk=bool(data.get("risk", False)))
