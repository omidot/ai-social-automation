from __future__ import annotations
import io, logging, os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import media
from .models import ArticleContent, PostContent

log = logging.getLogger("images")


def _gemini_image(prompt: str, size: tuple[int, int]) -> bytes:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.6-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for part in resp.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob and blob.data:
            return blob.data
    raise RuntimeError("gemini returned no image")


def _overlay_title(img_bytes: bytes, title: str, size: tuple[int, int]) -> Image.Image:
    W, H = size
    bg = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((W, H))
    bg = Image.alpha_composite(bg.convert("RGBA"),
                               Image.new("RGBA", (W, H), (0, 0, 0, 90))).convert("RGB")
    draw = ImageDraw.Draw(bg)
    font = ImageFont.truetype(str(media.FONT_PATH), 78)
    lines = media._wrap(draw, title.upper(), font, W - 140)
    line_h = 92
    y = H - 110 - line_h * len(lines)
    for ln in lines:
        x = (W - draw.textlength(ln, font=font)) / 2
        draw.text((x, y), ln, font=font, fill="white", stroke_width=4,
                  stroke_fill=(10, 10, 30))
        y += line_h
    return bg


def _legacy_fallback(article: ArticleContent, out_dir: Path,
                     size: tuple[int, int]) -> list[str]:
    stub = PostContent(
        angle="tin-tuc", caption_fb=article.caption_fb, caption_ig=article.caption_ig,
        hashtags=article.hashtags, thumbnail_prompt=article.cover_brief,
        thumbnail_title=article.cover_title, youtube_title="", youtube_desc="",
        tiktok_caption="", source_url=article.sources[0]["url"],
        source_name=article.sources[0]["name"])
    from .models import Candidate
    from datetime import datetime, timezone
    cand = Candidate(url=article.sources[0]["url"], title=article.cover_title,
                     source=article.sources[0]["name"],
                     published_at=datetime.now(timezone.utc))
    paths, _ = media.build_media(cand, stub, Path(out_dir), "")
    # media.build_media returns mixed sizes/aspect ratios (1200x630, 1280x720, ...);
    # Instagram rejects a carousel whose images are not all the same size, so
    # normalize every image to the spec size before returning.
    normed: list[str] = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        normed.append(str(media._save_jpeg(im, Path(p), size)))
    return normed


def build_images(article: ArticleContent, out_dir, *, style_prompt: str,
                 size: tuple[int, int], gen=None,
                 provider: str = "gemini") -> list[str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if provider == "legacy":
        return _legacy_fallback(article, out_dir, size)
    gen = gen or _gemini_image
    try:
        cover_bytes = gen(f"{article.cover_brief}, {style_prompt}", size)
        brief_bytes = [gen(f"{brief}, {style_prompt}", size)
                       for brief in article.image_briefs]
        cover = _overlay_title(cover_bytes, article.cover_title, size)
        paths = [str(media._save_jpeg(cover, out_dir / "01_cover.jpg"))]
        for i, b in enumerate(brief_bytes, start=2):
            im = Image.open(io.BytesIO(b)).convert("RGB").resize(size)
            paths.append(str(media._save_jpeg(im, out_dir / f"{i:02d}.jpg")))
        return paths
    except Exception as e:  # noqa: BLE001 - any Gemini-path failure (gen, decode, overlay, save) -> legacy
        log.warning("gemini image path failed (%s); using legacy media", e)
        return _legacy_fallback(article, out_dir, size)
