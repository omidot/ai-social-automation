from __future__ import annotations

from .llm import generate as _default_generate, parse_json_response, LLMError
from .models import Candidate, PostContent


class WriteError(Exception):
    pass


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
_DEEP_KEYS = ("caption_fb", "caption_ig", "hashtags", "cover_title", "cover_brief",
              "image_briefs")


def build_deep_prompt(cand, voice):
    system = (
        f"Bạn là biên tập viên tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Giọng: {voice.get('giong','')}. Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        "Viết bài CHUYÊN SÂU về MỘT tin. CHỈ trả về JSON với khoá: "
        "caption_fb (200-350 từ, xuống dòng, kết bằng CTA), caption_ig (<=60 từ), "
        "hashtags (8-15 chuỗi #), cover_title (4-10 từ tiếng Việt), "
        "cover_brief (tiếng Anh, tả ảnh, không chữ), "
        "image_briefs (3-4 chuỗi tiếng Anh tả ảnh minh hoạ, không chữ), risk (bool)."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = f"TIÊU ĐỀ: {cand.title}\nNGUỒN: {cand.source}\nURL: {cand.url}\n\n{article}\n"
    return system, user


def write_deep(cand, voice, generate=_default_generate):
    try:
        data = parse_json_response(generate(*build_deep_prompt(cand, voice), provider="auto"))
    except LLMError as e:
        raise WriteError(f"LLM failed: {e}") from e
    missing = [k for k in _DEEP_KEYS if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"deep response missing keys: {missing}")
    name = _source_name(cand)
    line = f"Nguồn: {name} — {cand.url}"
    cap = data["caption_fb"].rstrip()
    if line not in cap:
        cap = f"{cap}\n\n{line}"
    briefs = [b.strip() for b in data["image_briefs"] if b.strip()][:4]
    if len(briefs) < 3:
        briefs = (briefs + [data["cover_brief"]] * 3)[:3]
    from .models import ArticleContent
    return ArticleContent(
        format="deep", caption_fb=cap, caption_ig=data["caption_ig"].strip(),
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        cover_title=data["cover_title"].strip().upper(),
        cover_brief=data["cover_brief"].strip(), image_briefs=briefs,
        sources=[{"name": name, "url": cand.url}], risk=bool(data.get("risk", False)))


def build_roundup_prompt(cands, voice):
    items = "\n\n".join(
        f"[{i+1}] {c.title}\nNGUỒN: {_source_name(c)} — {c.url}\n"
        f"{(c.full_text or c.summary or '')[:1500]}"
        for i, c in enumerate(cands))
    system = (
        f"Bạn là biên tập viên tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Giọng: {voice.get('giong','')}. Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". {_ARTICLE_GUARDRAILS} "
        f"Viết bài GOM {len(cands)} tin, đánh số 1..{len(cands)}, mỗi tin 2-4 câu + link nguồn. "
        "CHỈ trả về JSON với khoá: caption_fb (đánh số, kết bằng câu hỏi tương tác), "
        "caption_ig (<=40 từ), hashtags (8-15 chuỗi #), cover_title (4-10 từ tiếng Việt), "
        "cover_brief (tiếng Anh, tả ảnh, không chữ), "
        f"image_briefs (ĐÚNG {len(cands)} chuỗi tiếng Anh, thứ tự khớp tin 1..{len(cands)}, "
        "tả ảnh, không chữ), risk (bool)."
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
    briefs = [b.strip() for b in data["image_briefs"] if b.strip()]
    if len(briefs) != len(cands):
        raise WriteError(f"roundup image_briefs {len(briefs)} != items {len(cands)}")
    from .models import ArticleContent
    return ArticleContent(
        format="roundup", caption_fb=data["caption_fb"].rstrip(),
        caption_ig=data["caption_ig"].strip(),
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        cover_title=data["cover_title"].strip().upper(),
        cover_brief=data["cover_brief"].strip(), image_briefs=briefs,
        sources=[{"name": _source_name(c), "url": c.url} for c in cands],
        risk=bool(data.get("risk", False)))
