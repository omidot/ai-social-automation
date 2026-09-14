from __future__ import annotations
import logging
import re
from pathlib import Path

import httpx

log = logging.getLogger("video.logos")

# Nguồn favicon công khai của Google -- một endpoint, mọi hãng, không cần
# khoá API và không phải nhúng sẵn logo có bản quyền vào repo.
_FAVICON = "https://www.google.com/s2/favicons"


class LogoError(Exception):
    pass


# Tên hãng/model xuất hiện trong lời nói -> tên hiển thị + domain lấy logo.
# Khoá là dạng đã chuẩn hoá (thường, bỏ dấu cách/chấm) để "GPT-6", "gpt 6",
# "GPT6" cùng khớp một mục.
BRANDS: dict[str, tuple[str, str]] = {
    "openai": ("OpenAI", "openai.com"),
    "chatgpt": ("OpenAI", "openai.com"),
    "gpt": ("OpenAI", "openai.com"),
    "sora": ("OpenAI", "openai.com"),
    "codex": ("OpenAI", "openai.com"),
    "anthropic": ("Anthropic", "anthropic.com"),
    "claude": ("Anthropic", "anthropic.com"),
    "fable": ("Anthropic", "anthropic.com"),
    "deepseek": ("DeepSeek", "deepseek.com"),
    "gemini": ("Google", "gemini.google.com"),
    "google": ("Google", "google.com"),
    "deepmind": ("Google DeepMind", "deepmind.google"),
    "meta": ("Meta", "meta.com"),
    "llama": ("Meta", "meta.com"),
    "grok": ("xAI", "x.ai"),
    "xai": ("xAI", "x.ai"),
    "mistral": ("Mistral", "mistral.ai"),
    "qwen": ("Qwen", "qwen.ai"),
    "alibaba": ("Alibaba", "alibaba.com"),
    "nvidia": ("NVIDIA", "nvidia.com"),
    "microsoft": ("Microsoft", "microsoft.com"),
    "copilot": ("Microsoft", "microsoft.com"),
    "perplexity": ("Perplexity", "perplexity.ai"),
    "midjourney": ("Midjourney", "midjourney.com"),
    "huggingface": ("Hugging Face", "huggingface.co"),
    "github": ("GitHub", "github.com"),
    "cursor": ("Cursor", "cursor.com"),
    "apple": ("Apple", "apple.com"),
    "amazon": ("Amazon", "amazon.com"),
    "tesla": ("Tesla", "tesla.com"),
}

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _key(word: str) -> str:
    return word.lower().replace("-", "").replace(".", "").replace(" ", "")


def detect_brands(text: str) -> list[str]:
    """Tên hãng nhắc tới trong ``text``, theo thứ tự xuất hiện, không lặp.

    Trả về khoá của BRANDS chứ không phải tên hiển thị, để phía gọi tra cứu
    được cả tên lẫn domain.
    """
    seen: list[str] = []
    for w in _WORD.findall(text or ""):
        k = _key(w)
        if k in BRANDS and k not in seen:
            seen.append(k)
    return seen


def fetch_logo(domain: str, dest: Path, *, size: int = 128, timeout: int = 10) -> Path:
    """Tải favicon của ``domain`` về ``dest``. Ném LogoError nếu không được."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest                      # đã có trong cache, không tải lại
    try:
        r = httpx.get(_FAVICON, params={"domain": domain, "sz": size},
                      timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as e:
        raise LogoError(f"logo request failed for {domain}: {e}") from e
    if r.status_code != 200 or not r.content:
        raise LogoError(f"logo HTTP {r.status_code} for {domain}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    log.info("logo: %s -> %s (%d bytes)", domain, dest, len(r.content))
    return dest


def collect_logos(text: str, public_dir: Path) -> dict[str, dict[str, str]]:
    """Tải logo cho mọi hãng nhắc trong ``text``.

    Trả về ``{khoá: {"label": tên hiển thị, "file": đường dẫn tương đối}}``.
    Hãng nào tải lỗi thì bỏ qua -- thiếu một logo không được phép làm hỏng
    cả video.
    """
    out: dict[str, dict[str, str]] = {}
    for k in detect_brands(text):
        label, domain = BRANDS[k]
        rel = f"logos/{k}.png"
        try:
            fetch_logo(domain, Path(public_dir) / rel)
        except LogoError as e:
            log.warning("logo for %s skipped (%s)", k, e)
            continue
        out[k] = {"label": label, "file": rel}
    return out
