from __future__ import annotations
import json, os, re, subprocess, time


class LLMError(Exception):
    pass


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_response(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    m = _JSON_RE.search(text)
    if not m:
        raise LLMError(f"no JSON object in model output: {text[:200]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMError(f"invalid JSON in model output: {e}") from e


def _claude(system: str, user: str, timeout: int) -> str:
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN not set")
    prompt = f"{system}\n\n{user}"
    proc = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude cli exit {proc.returncode}: {proc.stderr[:300]}")
    payload = json.loads(proc.stdout)
    if payload.get("is_error"):
        raise RuntimeError(f"claude returned error: {payload.get('result', '')[:300]}")
    return payload["result"]


_GEMINI_RETRIES = 3
_TRANSIENT_MARKERS = ("503", "429", "unavailable", "overloaded", "resource exhausted",
                      "resourceexhausted", "servererror", "rate limit")
_CLIENT_ERROR_MARKERS = ("400", "401", "403", "404", "invalid_argument",
                         "permission_denied", "unauthenticated", "not found",
                         "api key not valid")


def _is_transient(exc: Exception) -> bool:
    """True if the exception looks like a retryable transient server failure."""
    msg = str(exc).lower()
    if any(m in msg for m in _CLIENT_ERROR_MARKERS):
        return False
    return any(m in msg for m in _TRANSIENT_MARKERS)


def _gemini_call(client, model: str, contents: str, config):
    """Thin wrapper around the SDK call so tests can monkeypatch it."""
    return client.models.generate_content(model=model, contents=contents, config=config)


def _gemini(system: str, user: str, timeout: int) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    contents = f"{system}\n\n{user}"
    config = types.GenerateContentConfig(response_mime_type="application/json")
    last_exc = None
    for attempt in range(1, _GEMINI_RETRIES + 1):
        try:
            resp = _gemini_call(client, model, contents, config)
            return resp.text
        except Exception as e:  # noqa: BLE001 - narrowed by _is_transient below
            if not _is_transient(e) or attempt == _GEMINI_RETRIES:
                raise
            last_exc = e
            time.sleep(2 * attempt)
    raise last_exc  # pragma: no cover - loop always returns or raises above


_ORDER = {"auto": ["_claude", "_gemini"], "claude": ["_claude"], "gemini": ["_gemini"]}


def generate(system: str, user: str, provider: str = "auto", timeout: int = 90) -> str:
    backends = _ORDER.get(provider)
    if backends is None:
        raise LLMError(f"unknown provider {provider!r}")
    errors = []
    for name in backends:
        fn = globals()[name]
        try:
            return fn(system, user, timeout)
        except Exception as e:  # noqa: BLE001 - deliberate: try next backend
            errors.append(f"{name}: {e}")
    raise LLMError("all LLM backends failed -> " + " | ".join(errors))


_FAKE_LLM_JSON = json.dumps({
    "angle": "tin-tuc",
    "caption_fb": ("AI tuần này lại có biến. Đây là bản dựng thử ngoại tuyến của "
                   "pipeline, dùng để kiểm tra luồng chạy chứ chưa phải nội dung thật. "
                   "Bạn nghĩ sao? Comment cho mình biết nhé."),
    "caption_ig": "Bản dựng thử ngoại tuyến của pipeline. #AI",
    "hashtags": ["#AI", "#trituenhantao", "#congnghe", "#tin247", "#OpenAI",
                 "#chuyendoiso", "#automation", "#ahitofficial"],
    "thumbnail_prompt": "futuristic glowing neural network core, blue and violet, cinematic, no text",
    "thumbnail_title": "BẢN DỰNG THỬ PIPELINE",
    "youtube_title": "Bản dựng thử pipeline AI social automation",
    "youtube_desc": "Video mô tả sẽ được sinh tự động khi có khoá LLM. Nguồn trong mô tả.",
    "tiktok_caption": "Thử pipeline AI 👀 #AI #automation",
}, ensure_ascii=False)


def _fake_generate(system: str, user: str, **kwargs) -> str:
    return _FAKE_LLM_JSON
