from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from .daily_state import DailyState
from .llm import parse_json_response

log = logging.getLogger("topics")

_LIVE_STATUS = {"draft", "scheduled", "posted", "publishing"}


class TopicError(Exception):
    pass


def load_topics(root: Path) -> dict:
    """Read config/topics.yaml (curated topic bank)."""
    p = Path(root) / "config" / "topics.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _parse_date(stem: str) -> date | None:
    try:
        return datetime.strptime(stem, "%Y-%m-%d").date()
    except ValueError:
        return None


def recent_titles(root: Path, days: int) -> list[str]:
    """Titles used by any live slot in the last ``days`` days, newest file first,
    deduped. A corrupt daily file is skipped (load_safe logs it)."""
    ds = DailyState(Path(root) / "data")
    today = datetime.now(timezone.utc).date()
    out: list[str] = []
    seen: set[str] = set()
    for path in reversed(ds.all_files()):
        d = _parse_date(path.stem)
        if d is None or (today - d).days > days or (today - d).days < 0:
            continue
        doc = ds.load_safe(path.stem)
        if doc is None:
            continue
        for slot in doc.get("posts", {}).values():
            title = (slot or {}).get("title")
            if not title or slot.get("status") not in _LIVE_STATUS:
                continue
            if title not in seen:
                seen.add(title)
                out.append(title)
    return out


def _build_prompt(topics: dict, recent: list[str], voice: dict) -> tuple[str, str]:
    ten_kenh = voice.get("ten_kenh", "")
    system = (
        f"Bạn là người lên chủ đề nội dung cho kênh \"{ten_kenh}\" về AI, năng suất "
        "và kiếm tiền online cho khán giả Việt Nam. "
        "Hãy đề xuất ĐÚNG MỘT chủ đề cụ thể, thực dụng mà người ta thật sự tìm kiếm "
        "và muốn đọc. Chủ đề có thể lấy từ danh sách 'seeds', ghép một 'format' với "
        "một 'theme', hoặc là một ý tưởng mới cùng tinh thần đó. "
        "Chủ đề phải CỤ THỂ (nêu rõ số lượng hoặc việc cụ thể), hữu ích, và KHÔNG "
        "được trùng hay xào lại bất cứ mục nào trong danh sách 'đã đăng gần đây'. "
        "CHỈ trả về JSON: {\"topic\": chuỗi <=14 từ, "
        "\"angle\": một câu nêu bài này sẽ giúp người đọc làm được gì}."
    )
    recent_block = "\n".join(f"- {t}" for t in recent[:30]) or "(chưa có)"
    user = (
        "ĐÃ ĐĂNG GẦN ĐÂY (tránh lặp lại):\n"
        f"{recent_block}\n\n"
        "NGÂN HÀNG CHỦ ĐỀ (config/topics.yaml):\n"
        f"{yaml.safe_dump(topics, allow_unicode=True, sort_keys=False)}"
    )
    return system, user


def propose_topic(topics: dict, recent: list[str], voice: dict, generate) -> dict:
    """One LLM call: propose a single specific, non-repeated topic + angle."""
    system, user = _build_prompt(topics, recent, voice)
    raw = generate(system, user, provider="auto")
    try:
        data = parse_json_response(raw)
    except Exception as e:  # noqa: BLE001 - normalise to TopicError
        raise TopicError(f"topic proposal not JSON: {e}") from e
    if not isinstance(data, dict):
        raise TopicError(f"topic proposal wrong shape: {type(data).__name__}")
    topic = str(data.get("topic", "")).strip()
    if not topic:
        raise TopicError(f"topic proposal missing 'topic': {data!r}")
    angle = str(data.get("angle", "")).strip()
    log.info("proposed topic: %s | angle: %s", topic, angle)
    return {"topic": topic, "angle": angle}
