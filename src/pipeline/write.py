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
ANGLES = frozenset({"tin-nong", "quan-diem", "xu-huong", "chuyen-thuc-chien"})
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
    "Trả lại ĐÚNG JSON với 'slides' là mảng 4-9 object: object đầu role 'hook', "
    "object cuối role 'close', mọi object ở giữa role 'item'. Mỗi 'item' cần "
    "\"body\" 40-70 từ giải thích cụ thể (có ví dụ/con số/bước làm), KHÔNG một dòng "
    "cụt. Giữ nguyên nội dung, chỉ sửa cấu trúc."
)

# The `slides` contract, shared by build_share_prompt + build_take_prompt so the
# storyboard rules stay in one place.
_STORYBOARD_SPEC = (
    "slides (mảng 4-9 object storyboard — SỐ LƯỢNG KHÔNG CỐ ĐỊNH, tự quyết theo "
    "nội dung): object ĐẦU role 'hook', object CUỐI role 'close', MỌI object ở "
    "giữa role 'item'. "
    "HOOK = {\"role\":\"hook\", \"headline\": CÂU HOOK GÂY TÒ MÒ <=9 từ (ngắn, "
    "mạnh, khiến người ta dừng lại — KHÔNG phải tiêu đề mô tả), \"body\": MỘT câu "
    "phụ <=28 từ nói rõ người đọc sắp nhận được gì, "
    "\"tools\": [ {\"name\": <tên sản phẩm>, \"domain\": <domain chính thức>}, ... ] "
    "— 0 đến 6 sản phẩm mà carousel sẽ nói tới, để slide hook hiện logo; để [] nếu "
    "bài KHÔNG xoay quanh sản phẩm cụ thể}. "
    "ITEM = {\"role\":\"item\", \"headline\": <=9 từ, "
    "\"body\": 40-70 TỪ, CỤ THỂ — có ví dụ / con số / bước làm thật, TUYỆT ĐỐI "
    "KHÔNG một dòng cụt, "
    "\"tool\": {\"name\", \"domain\"} khi item nói về MỘT sản phẩm có thật, hoặc "
    "null, "
    "\"bullets\": [ tối đa 3 dòng, mỗi dòng <=10 từ ] hoặc []}. "
    "CLOSE = {\"role\":\"close\", \"headline\": <=9 từ, \"body\": <=40 từ}. "
    "Các slide 'item' phải bám ĐÚNG mạch của hook. "
    "Nhiều bài (quan-diem / xu-huong / tin-nong không xoay quanh một sản phẩm cụ thể) "
    "sẽ có hook.tools = [] và mọi item.tool = null — đó là BÌNH THƯỜNG, không phải "
    "thiếu sót. "
    "Khi nhắc tới một sản phẩm/công cụ CÓ THẬT, BẮT BUỘC điền \"domain\" gốc chính "
    "thức (vd openai.com, deepmind.google, anthropic.com, canva.com, "
    "elevenlabs.io, runwayml.com, capcut.com, notion.so) và gom tất cả sản phẩm "
    "được nhắc vào hook.tools (tối đa 6). Chỉ dùng công cụ bạn CHẮC CHẮN có thật "
    "và domain đúng — KHÔNG bịa domain; không chắc thì để \"tool\": null. "
    "cover_title = CHÍNH câu hook (<=9 từ)"
)


def _validate_slide_roles(slides) -> None:
    """Enforce the storyboard shape: a list of 4 to 9 slide dicts whose first
    slide is role 'hook', last is role 'close', and every middle slide is role
    'item'. Raises ``WriteError`` with a precise Vietnamese message on any
    violation."""
    if not isinstance(slides, list) or not (4 <= len(slides) <= 9):
        n = len(slides) if isinstance(slides, list) else type(slides).__name__
        raise WriteError(f"cần 4-9 slide, có {n}")
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


def _clean_domain(raw: str) -> str:
    d = str(raw).strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d).strip("/").split("/")[0]
    return d


def _normalise_tool(raw, idx: int | str | None = None) -> dict | None:
    """Return ``{"name", "domain"}`` for a genuine product, ``None`` when there
    is no tool. A ``tool`` that is *present* but malformed (not an object, or
    missing / bogus ``name`` or ``domain``) raises ``WriteError`` — the model is
    told the shape, so a broken one is a real error, not a slide-render detail.

    An explicitly empty object (``{}`` / all-blank values) counts as "no tool".
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise WriteError(f"slide {idx} 'tool' phải là object {{name, domain}} hoặc null")
    name = str(raw.get("name", "")).strip()
    domain = _clean_domain(raw.get("domain", ""))
    if not name and not domain:
        return None
    if not name or not domain:
        raise WriteError(f"slide {idx} 'tool' phải có cả 'name' và 'domain'")
    if "." not in domain or " " in domain:
        raise WriteError(f"slide {idx} 'tool' domain không hợp lệ: {domain!r}")
    return {"name": name, "domain": domain}


def _normalise_tools(raw, idx: int | str | None = None) -> list[dict]:
    """The hook's ``tools`` list: 0-6 ``{"name", "domain"}`` products. Missing /
    empty -> ``[]``. A non-list, more than 6 entries, or a malformed entry raise
    ``WriteError`` (each entry goes through ``_normalise_tool``)."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise WriteError(f"slide {idx} 'tools' phải là mảng")
    if len(raw) > 6:
        raise WriteError(f"slide {idx} 'tools' tối đa 6, có {len(raw)}")
    out: list[dict] = []
    for t in raw:
        nt = _normalise_tool(t, idx)
        if nt:
            out.append(nt)
    return out


def _normalise_bullets(raw) -> list[str]:
    """0-3 short bullet strings, URLs stripped, blanks dropped, capped at 3.
    Over-long bullets are kept (the layout wraps) — only shape errors raise."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise WriteError("'bullets' phải là mảng chuỗi")
    out: list[str] = []
    for b in raw:
        t = _strip_urls(str(b).strip())
        if t:
            out.append(t)
        if len(out) == 3:
            break
    return out

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


def build_share_prompt(cand: Candidate, voice: dict, sibling_angle: str = "") -> tuple[str, str]:
    """System + user prompt for the launch-analysis writer.

    The piece is ONE person analysing ONE noteworthy AI-world event — in the
    channel's sharing voice, NOT a reporter, NOT a numbered news round-up. The
    source no longer has to be a fresh product launch: rumor, analysis, funding,
    research, benchmark, controversy, or policy all qualify.
    """
    sibling_line = (
        f"Slot kia hôm nay đã dùng góc \"{sibling_angle}\" — nếu hợp lý, chọn góc "
        "khác cho đa dạng. " if sibling_angle else ""
    )
    system = (
        f"Bạn là người viết tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        f"{_IMAN_VOICE} "
        "NHIỆM VỤ: bài nguồn nói về MỘT chuyện đáng chú ý trong giới AI — có thể là "
        "ra mắt sản phẩm, rò rỉ/tin đồn, phân tích, gọi vốn, kết quả nghiên cứu, "
        "benchmark, tranh cãi, hay chính sách. Viết một bài PHÂN TÍCH/CHIA SẺ về "
        "chuyện đó, bằng giọng CHIA SẺ của kênh — KHÔNG phải phóng viên, KHÔNG phải "
        "một bản tin, KHÔNG đánh số danh sách tin. "
        f"{sibling_line}"
        "Chọn 'angle' HỢP NHẤT với tin, một trong bốn: "
        "tin-nong (chuyện vừa xảy ra — 'tin này dạy mình điều gì'), "
        "quan-diem (phản biện cách hiểu số đông về chuyện này), "
        "xu-huong (tin này nằm trong một cú dịch chuyển lớn hơn — nêu cú dịch "
        "chuyển đó và nó ảnh hưởng tới người đọc thế nào), "
        "chuyen-thuc-chien (rút ra được cách áp dụng thật, kể như trải nghiệm). "
        "Mở bằng câu hook gây tò mò — KHÔNG mở bằng \"Công ty X vừa công bố...\". "
        "Nếu angle là tin-nong/xu-huong, các slide item bám mạch: (a) chuyện gì "
        "→ (b) nó thực sự nghĩa là gì, dùng chi tiết THẬT trong bài nguồn → "
        "(c) khác gì trước đây → (d) ảnh hưởng tới bạn thế nào → (e) nên làm gì. "
        "Nếu angle là quan-diem: nêu cách hiểu phổ biến → vì sao nó thiếu/sai → "
        "góc đúng hơn → hệ quả. "
        "Nếu angle là chuyen-thuc-chien: bối cảnh → thử thế nào → vướng gì → "
        "bài học rút ra. "
        "Mỗi item body 40-70 từ, cụ thể, dùng chi tiết THẬT trong bài nguồn — "
        "KHÔNG bịa số liệu. "
        "caption_fb: 200-350 từ, VIẾT THÀNH ĐOẠN VĂN MẠCH LẠC (xuống dòng giữa các "
        "ý), TUYỆT ĐỐI KHÔNG đánh số \"1. 2. 3.\", không phải danh sách tin, KHÔNG "
        "chèn URL. Giọng dứt khoát, chia sẻ, \"mình\"/\"bạn\", có chính kiến, không "
        "PR sáo rỗng, không hàn lâm. Kết bằng một câu hỏi. "
        "caption_ig: <=50 từ, cùng tinh thần. "
        "CHỈ trả về một object JSON hợp lệ với đúng các khoá: "
        "angle (một trong bốn mã ở trên), "
        "caption_fb, caption_ig, hashtags (mảng 8-15 chuỗi bắt đầu bằng #), "
        "cover_title (<=9 từ, chính là câu hook), "
        f"{_STORYBOARD_SPEC}, "
        "risk (bool). Toàn bộ tiếng Việt. "
        "Nếu bài nguồn KHÔNG liên quan AI, hoặc không có đủ dữ kiện cụ thể để viết, "
        "trả về ĐÚNG JSON {\"skip\": true, \"reason\": \"...\"} và không gì khác."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = (
        f"TIÊU ĐỀ: {cand.title}\n"
        f"NGUỒN: {cand.source}\n"
        f"URL: {cand.url}\n\n"
        f"NỘI DUNG BÀI GỐC:\n{article}\n"
    )
    return system, user


_ITEM_BODY_MIN_WORDS = 25   # "40-70 từ" target; anything under this is a stub


def _validate_share(data: dict) -> list[dict]:
    """Validate one raw ``share`` payload and return the normalised slide list.

    Raises ``WriteError`` with a precise message on any shape problem: missing
    keys, hashtags not a list, slide count outside 4-9, wrong hook/item/close
    role at index i, an item ``body`` far too short to be an explanation, or a
    malformed ``tool`` / ``tools`` entry.

    Normalised per-role shape:
      hook  -> {"role", "headline", "body", "tools": [ {name, domain}, ... ]}
      item  -> {"role", "headline", "body", "tool": {name,domain}|None,
                "bullets": [str]}
      close -> {"role", "headline", "body"}
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
        role = str(s.get("role", "")).strip().lower()
        headline = _strip_urls(str(s.get("headline", "")).strip())
        body = _strip_urls(str(s.get("body", "")).strip())
        if not headline:
            raise WriteError(f"slide {i} thiếu headline")

        if role == "hook":
            slides.append({
                "role": "hook", "headline": headline, "body": body,
                "tools": _normalise_tools(s.get("tools"), i),
            })
        elif role == "close":
            if len(body.split()) > 45:
                raise WriteError(
                    f"slide {i} (close) body quá dài ({len(body.split())} từ) — cần <=40 từ")
            slides.append({"role": "close", "headline": headline, "body": body})
        else:  # item
            n = len(body.split())
            if n < _ITEM_BODY_MIN_WORDS:
                raise WriteError(
                    f"slide {i} body quá ngắn ({n} từ) — cần 40-70 từ, giải thích cụ thể")
            slides.append({
                "role": "item", "headline": headline, "body": body,
                "tool": _normalise_tool(s.get("tool"), i),
                "bullets": _normalise_bullets(s.get("bullets")),
            })
    return slides


def write_share(cand: Candidate, voice: dict, sibling_angle: str = "",
                generate=_default_generate):
    """Turn one candidate into a single-topic knowledge-share article
    (``format="share"``) with a 4-to-9-slide hook / item... / close storyboard
    and a validated ``angle`` (see ``ANGLES``).

    The LLM often returns a wrong-shaped payload (slide count out of range,
    hook/close not at the ends, invalid angle). Mirror ``video/script.py``:
    validate, and on failure retry once with a correction nudge. A dead backend
    (``LLMError`` from the ``generate`` call itself) is *not* retried; a
    JSON-parse or validation failure — a model-output problem — is.
    """
    system, user = build_share_prompt(cand, voice, sibling_angle)

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
            angle = str(data.get("angle", "")).strip()
            if angle not in ANGLES:
                raise WriteError(f"angle không hợp lệ: {angle!r}")
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
            risk=bool(data.get("risk", False)),
            angle=angle)
    raise WriteError("unreachable")  # for type-checkers


def build_take_prompt(topic: str, angle: str, why: str, voice: dict) -> tuple[str, str]:
    """System + user prompt for the knowledge-sourced (fallback) writer.

    No source article — the model writes ``topic`` from its own knowledge, in the
    same Iman-Gadzhi sharing voice and 4-9-slide storyboard as ``write_share``.
    Only ever called with angle 'quan-diem' or 'xu-huong' (see topics.propose_topic).
    """
    system = (
        f"Bạn là người viết tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        f"{_IMAN_VOICE} "
        f"Đây là bài KHÔNG có bài nguồn — viết từ hiểu biết chung, góc \"{angle}\". "
        "KHÔNG bịa số liệu cụ thể; nếu cần ví dụ, dùng ví dụ chung/định tính thay vì "
        "một con số bạn không chắc. "
        "hook.tools PHẢI là [] và mọi item.tool PHẢI là null — bài này không xoay "
        "quanh một sản phẩm cụ thể. "
        "caption_fb: 200-350 từ, VIẾT THÀNH ĐOẠN VĂN MẠCH LẠC, TUYỆT ĐỐI KHÔNG đánh "
        "số \"1. 2. 3.\", KHÔNG chèn URL. Kết bằng một câu hỏi. "
        "caption_ig: <=50 từ, cùng tinh thần. "
        "CHỈ trả về một object JSON hợp lệ với đúng các khoá: "
        "caption_fb, caption_ig, hashtags (mảng 8-15 chuỗi bắt đầu bằng #), "
        "cover_title (<=9 từ, chính là câu hook), "
        f"{_STORYBOARD_SPEC}, "
        "risk (bool). Toàn bộ tiếng Việt. "
        "Nếu bạn không đủ hiểu biết chắc chắn để viết chủ đề này, trả về ĐÚNG JSON "
        "{\"skip\": true, \"reason\": \"...\"} và không gì khác."
    )
    user = f"CHỦ ĐỀ: {topic}\nGÓC: {angle}\nÝ: {why}\n"
    return system, user


def write_take(topic: str, angle: str, why: str, voice: dict,
               generate=_default_generate):
    """Write a single-topic opinion/trend article (``format="share"``) from the
    model's own knowledge — the fallback bank's writer. Same 2-attempt
    retry-with-``[SỬA]``-nudge loop and 4-9-slide validation as ``write_share``.
    ``sources`` is empty, ``angle`` is the caller-supplied value (not re-derived
    from the model), and no ``Nguồn:`` line is appended.
    """
    system, user = build_take_prompt(topic, angle, why, voice)

    for attempt in (1, 2):
        log.info("write_take attempt %d", attempt)
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
            log.warning("write_take attempt %d rejected: %s", attempt, e)
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
            risk=bool(data.get("risk", False)),
            angle=angle)
    raise WriteError("unreachable")  # for type-checkers
