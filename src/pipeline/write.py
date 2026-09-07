from __future__ import annotations

import logging
import re

from .llm import generate as _default_generate, parse_json_response, LLMError
from .models import Candidate, PostContent

log = logging.getLogger("write")


class WriteError(Exception):
    pass


class _Decline(WriteError):
    """The model was explicitly told it *may* refuse a source that isn't about
    AI / lacks facts, by returning ``{"skip": true, "reason": "..."}``. That is
    a legitimate machine-readable signal, not a formatting slip — so it must
    NOT consume a nudge-retry. Subclasses ``WriteError`` so callers that catch
    ``WriteError`` (article_run's fall-through loop) still handle it."""


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

_SHARE_KEYS = ("caption_fb", "caption_ig", "hashtags", "cover_title", "slides")

# The [SỬA] nudge appended when the model returns a wrong-shaped storyboard.
_SHAPE_NUDGE = (
    "Trả lại ĐÚNG JSON với 'slides' là mảng 5-7 object: object đầu role 'hook', "
    "object cuối role 'close', mọi object ở giữa role 'item'. Giữ nguyên nội dung, "
    "chỉ sửa cấu trúc."
)

# The `slides` contract, shared by build_share_prompt + build_topic_prompt so the
# storyboard rules stay in one place.
_STORYBOARD_SPEC = (
    "slides (mảng 5-7 object storyboard — KHÔNG cố định 5): object ĐẦU role "
    "'hook', object CUỐI role 'close', MỌI object ở giữa role 'item'. Mỗi object: "
    "{\"role\": <role>, \"headline\": <=8 từ, \"body\": <=24 từ, "
    "\"tool\": {\"name\": <tên công cụ>, \"domain\": <domain gốc chính thức>} hoặc null}. "
    "slides[0].headline PHẢI là CÂU HOOK GÂY TÒ MÒ — ngắn, mạnh, khiến người ta "
    "dừng lại; KHÔNG phải tiêu đề mô tả. Ví dụ tốt: \"5 công cụ AI ít ai biết\", "
    "\"Bạn đang dùng AI sai cách\", \"Thứ này thay cả ê-kíp dựng phim\". "
    "slides[0].body là MỘT câu phụ ngắn nói rõ người đọc sắp nhận được gì. "
    "Các slide 'item' phải bám ĐÚNG mạch của hook: hook nói \"Top 5 công cụ\" thì "
    "có ĐÚNG 5 slide item, mỗi slide MỘT công cụ; hook nói \"quy trình N bước\" "
    "thì mỗi item là một bước theo thứ tự. "
    "Khi một item nói về một công cụ CÓ THẬT, BẮT BUỘC điền \"tool\" với tên đúng "
    "và domain gốc chính thức (vd openai.com, canva.com, elevenlabs.io, "
    "capcut.com, notion.so). Chỉ dùng công cụ bạn CHẮC CHẮN có thật và domain "
    "đúng — KHÔNG bịa domain; không chắc thì để \"tool\": null. "
    "cover_title = CHÍNH câu hook (<=9 từ)"
)


def _validate_slide_roles(slides) -> None:
    """Enforce the storyboard shape: a list of 5 to 7 slide dicts whose first
    slide is role 'hook', last is role 'close', and every middle slide is role
    'item'. Raises ``WriteError`` with a precise Vietnamese message on any
    violation."""
    if not isinstance(slides, list) or not (5 <= len(slides) <= 7):
        n = len(slides) if isinstance(slides, list) else type(slides).__name__
        raise WriteError(f"cần 5-7 slide, có {n}")
    roles = [
        str(s.get("role", "")).strip().lower() if isinstance(s, dict) else ""
        for s in slides
    ]
    if roles[0] != "hook":
        raise WriteError("slide đầu phải role 'hook'")
    if roles[-1] != "close":
        raise WriteError("slide cuối phải role 'close'")
    for i in range(1, len(slides) - 1):
        if roles[i] != "item":
            raise WriteError(f"slide {i} phải role 'item'")


def _normalise_tool(raw) -> dict | None:
    """Return ``{"name", "domain"}`` when ``raw`` names a real product with a
    plausible root domain, else ``None``. A bare / malformed ``tool`` is dropped
    rather than raising — the slide just renders its fallback icon."""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    domain = str(raw.get("domain", "")).strip().lower()
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain).strip("/").split("/")[0]
    if not name or not domain or "." not in domain or " " in domain:
        return None
    return {"name": name, "domain": domain}

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
        "cover_title (<=9 từ, chính là câu hook), "
        f"{_STORYBOARD_SPEC}, "
        "risk (bool). Toàn bộ tiếng Việt. "
        "Nếu bài nguồn KHÔNG nói về AI hoặc không đủ dữ kiện để viết, trả về "
        "ĐÚNG JSON {\"skip\": true, \"reason\": \"...\"} và không gì khác."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = (
        f"TIÊU ĐỀ: {cand.title}\n"
        f"NGUỒN: {cand.source}\n"
        f"URL: {cand.url}\n\n"
        f"NỘI DUNG BÀI GỐC:\n{article}\n"
    )
    return system, user


def _validate_share(data: dict) -> list[dict]:
    """Validate one raw ``share`` payload and return the normalised slide list.

    Raises ``WriteError`` with a precise message on any shape problem (missing
    keys, hashtags not a list, slide count outside 5-7, wrong hook/item/close
    role at index i).
    """
    missing = [k for k in _SHARE_KEYS if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"share response missing keys: {missing}")
    if not isinstance(data["hashtags"], list):
        raise WriteError("hashtags must be a list")

    raw_slides = data["slides"]
    _validate_slide_roles(raw_slides)
    slides: list[dict] = []
    for i, s in enumerate(raw_slides):
        if not isinstance(s, dict):
            raise WriteError(f"slide {i} is not an object")
        slides.append({
            "role": str(s.get("role", "")).strip().lower(),
            "headline": _strip_urls(str(s.get("headline", "")).strip()),
            "body": _strip_urls(str(s.get("body", "")).strip()),
            "tool": _normalise_tool(s.get("tool")),
        })
    return slides


def write_share(cand: Candidate, voice: dict, generate=_default_generate):
    """Turn one candidate into a single-topic knowledge-share article
    (``format="share"``) with a 5-to-7-slide hook / item... / close storyboard.

    The LLM often returns a wrong-shaped payload (slide count out of range,
    hook/close not at the ends). Mirror ``video/script.py``: validate, and on failure retry
    once with a correction nudge. A dead backend (``LLMError`` from the
    ``generate`` call itself) is *not* retried; a JSON-parse or validation
    failure — a model-output problem — is.
    """
    system, user = build_share_prompt(cand, voice)

    for attempt in (1, 2):
        log.info("write_share attempt %d", attempt)
        try:
            raw = generate(system, user, provider="auto")
        except LLMError as e:  # backend down — retrying won't help
            raise WriteError(f"LLM failed: {e}") from e
        try:
            data = parse_json_response(raw)
            if isinstance(data, dict) and data.get("skip"):
                raise _Decline(
                    f"nguồn không phù hợp: {str(data.get('reason', ''))[:200]}")
            slides = _validate_share(data)
        except _Decline:  # a legitimate, machine-readable refusal — do NOT retry
            raise
        except (LLMError, WriteError) as e:  # bad model output — retryable
            if attempt == 2:
                raise e if isinstance(e, WriteError) else WriteError(f"LLM failed: {e}")
            log.warning("write_share attempt %d rejected: %s", attempt, e)
            user = user + f"\n\n[SỬA] Bản vừa rồi sai định dạng: {e}. " + _SHAPE_NUDGE
            continue

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
    raise WriteError("unreachable")  # for type-checkers


def build_topic_prompt(topic: str, angle: str, voice: dict) -> tuple[str, str]:
    """System + user prompt for the knowledge-sourced writer.

    No article to work from — the model writes ``topic`` from its own knowledge,
    same single-person sharing voice and 5-7-slide storyboard as ``write_share``.
    """
    system = (
        f"Bạn là người viết tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        f"Viết về ĐÚNG chủ đề: \"{topic}\". Góc: {angle}. "
        "GIỌNG: người chia sẻ hiểu biết, dứt khoát, có chính kiến, xưng \"mình\" "
        "gọi \"bạn\", câu ngắn. KHÔNG phải bản tin. Trong caption_fb KHÔNG đánh số "
        "kiểu \"1. 2. 3.\" — viết thành đoạn văn mạch lạc; nếu chủ đề là \"top N\" "
        "thì vẫn kể liền mạch, mỗi công cụ/bước một đoạn ngắn, KHÔNG dùng đầu mục "
        "đánh số. "
        "NỘI DUNG phải CỤ THỂ và DÙNG ĐƯỢC: nêu tên công cụ thật, bước làm thật, "
        "con số thật mà bạn chắc chắn. Nếu không chắc một chi tiết thì nói chung "
        "chung thay vì bịa. "
        "Cấu trúc suy nghĩ: hook → cụ thể là gì → người đọc được gì → cách bắt đầu "
        "→ chốt. "
        "caption_fb: 180-320 từ, xuống dòng giữa các ý, KHÔNG chèn URL. "
        "caption_ig: <=50 từ, cùng tinh thần, KHÔNG chèn URL. "
        "CHỈ trả về một object JSON hợp lệ với đúng các khoá: "
        "caption_fb, caption_ig, hashtags (mảng 8-15 chuỗi bắt đầu bằng #), "
        "cover_title (<=9 từ), "
        f"{_STORYBOARD_SPEC}, "
        "risk (bool). Toàn bộ tiếng Việt. "
        "Nếu bạn không đủ hiểu biết chắc chắn để viết chủ đề này, trả về ĐÚNG JSON "
        "{\"skip\": true, \"reason\": \"...\"} và không gì khác."
    )
    user = f"CHỦ ĐỀ: {topic}\nGÓC: {angle}\n"
    return system, user


def write_topic_post(topic: str, angle: str, voice: dict, generate=_default_generate):
    """Write a single-topic knowledge-share article (``format="share"``) from the
    model's own knowledge instead of a source article.

    Same 2-attempt retry-with-``[SỬA]``-nudge loop, same ``{"skip": true}``
    handling and the same 5-7-slide validation as ``write_share``. ``sources`` is
    empty and no ``Nguồn:`` line is appended.
    """
    system, user = build_topic_prompt(topic, angle, voice)

    for attempt in (1, 2):
        log.info("write_topic_post attempt %d", attempt)
        try:
            raw = generate(system, user, provider="auto")
        except LLMError as e:  # backend down — retrying won't help
            raise WriteError(f"LLM failed: {e}") from e
        try:
            data = parse_json_response(raw)
            if isinstance(data, dict) and data.get("skip"):
                raise _Decline(
                    f"chủ đề không viết được: {str(data.get('reason', ''))[:200]}")
            slides = _validate_share(data)
        except _Decline:  # a legitimate, machine-readable refusal — do NOT retry
            raise
        except (LLMError, WriteError) as e:  # bad model output — retryable
            if attempt == 2:
                raise e if isinstance(e, WriteError) else WriteError(f"LLM failed: {e}")
            log.warning("write_topic_post attempt %d rejected: %s", attempt, e)
            user = user + f"\n\n[SỬA] Bản vừa rồi sai định dạng: {e}. " + _SHAPE_NUDGE
            continue

        cap = _strip_urls(data["caption_fb"])
        cap_ig = _strip_urls(data["caption_ig"])

        from .models import ArticleContent
        return ArticleContent(
            format="share", caption_fb=cap, caption_ig=cap_ig,
            hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
            cover_title=str(data["cover_title"]).strip(),
            slides=slides,
            sources=[],
            risk=bool(data.get("risk", False)))
    raise WriteError("unreachable")  # for type-checkers
