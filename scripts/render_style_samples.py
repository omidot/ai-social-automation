"""Render a sample carousel for one or more of the 24 named styles so a human
can eyeball the layout. Writes JPEGs under ``scratchpad/style_samples/<name>/``.

Usage:
    python scripts/render_style_samples.py                 # all styles
    python scripts/render_style_samples.py white-centered navy-centered
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pipeline import images, styles
from pipeline.models import ArticleContent

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scratchpad" / "style_samples"

_BODY = ("Mô hình nhận một câu mô tả tiếng Việt rồi trả về đoạn phim tám giây ở "
         "1080p, giữ khuôn mặt nhân vật ổn định qua từng cảnh để bạn cắt ghép "
         "thành một video thật, chứ không chỉ là bản trình diễn cho vui mắt, và "
         "xuất ra được ngay trong trình duyệt mà không cần cài thêm gì cả.")

_TOOLS = [{"name": "Sora", "domain": "openai.com"},
          {"name": "Veo", "domain": "deepmind.google"},
          {"name": "Runway", "domain": "runwayml.com"}]


def _story() -> ArticleContent:
    slides = [
        {"role": "hook", "headline": "AI dựng phim tám giây trong trình duyệt",
         "body": "Ba công cụ vừa mở cửa cho bất kỳ ai thử ngay hôm nay.",
         "tools": _TOOLS},
    ]
    for i, tool in enumerate(_TOOLS, 1):
        slides.append({
            "role": "item", "headline": f"Việc số {i}: {tool['name']} làm được gì",
            "body": _BODY, "tool": tool,
            "bullets": ["nhập mô tả bằng tiếng Việt", "xuất 1080p trong một phút",
                        "giữ nhân vật ổn định giữa các cảnh"]})
    slides.append({"role": "close", "headline": "Chốt lại",
                   "body": "Kỹ năng mới không phải dựng hình — mà là viết mô tả "
                           "đủ rõ để cỗ máy hiểu ý bạn."})
    return ArticleContent(format="share", caption_fb="fb", caption_ig="ig",
                          hashtags=["#AI"], cover_title="AI DỰNG PHIM 8 GIÂY",
                          slides=slides, sources=[{"name": "src", "url": "http://x"}])


def main(argv: list[str]) -> None:
    by_name = {s.name: s for s in styles.load_styles(ROOT)}
    names = argv or list(by_name)
    for name in names:
        st = by_name.get(name)
        if st is None:
            print(f"!! unknown style {name!r}; known: {', '.join(by_name)}")
            continue
        dest = OUT / name
        paths = images.build_images(_story(), dest, size=(1080, 1350),
                                    brand={}, root=ROOT, style=st)
        print(f"{name:16s} -> {len(paths)} slides in {dest}")
        for p in paths:
            print(f"    {p}")


if __name__ == "__main__":
    main(sys.argv[1:])
