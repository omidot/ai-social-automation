"""Dựng lại trạng thái làm việc để render video demo bằng audio thật.

Các file trung gian (voice.mp3, words.json, cards.mjs, timeline.json...) đều
là sản phẩm sinh ra, không commit vào repo -- nên mỗi lần dọn repo là mất, và
dựng tay lại từng bước rất dễ sót. Script này dựng đủ một lượt:

    .venv/Scripts/python.exe scripts/stage_demo.py

Nó KHÔNG đụng tới pipeline thật; chỉ phục vụ việc xem trước bằng bản thu và
kịch bản đã có sẵn trên máy.
"""
from __future__ import annotations
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

AUDIO = [Path(rf"C:\Users\Admin\Downloads\{n}.mp3") for n in (1, 2, 3)]
SCRIPT = Path("D:/Temp/claude/D--Automation-Social/2318d7b5-0602-4531-93bc-d431ecd0a839"
              "/scratchpad/real_script.json")
SOURCES = [
    "https://openai.com/index/cognition-devin-testing-with-astra",
    "https://techcrunch.com/2026/09/10/openai-puts-pro-subscriptions-on-hold-due-to-astra-demand/",
]

log = logging.getLogger("stage")


class LocalTG:
    """Thay cho Telegram: đọc thẳng file trên máy."""

    def download_file(self, file_id, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(file_id, dest)
        return str(dest)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from pipeline.video import align as _align, codegen, render as _render, sourceshot, transcribe
    from pipeline.video import portrait
    from pipeline.video.models import Script

    vd = ROOT / "video"

    missing = [p for p in AUDIO if not p.is_file()]
    if missing or not SCRIPT.is_file():
        log.error("thiếu đầu vào: %s", missing or SCRIPT)
        return 1

    # 1. ghép audio nhiều phần -> voice.mp3
    parts = [{"file_id": str(p), "name": p.name} for p in AUDIO]
    joined = _render._fetch_voice({"audio_parts": parts}, LocalTG(), vd)
    shutil.copy(joined, vd / "public/voice.mp3")

    # 2. nhận diện giọng nói -> mốc giờ từng từ
    transcribe.transcribe_words(vd / "public/voice.mp3", vd / "ref/words.json")

    # 3. kịch bản -> cards.mjs / variants.mjs
    codegen.write(Script.from_dict(json.loads(SCRIPT.read_text(encoding="utf-8"))), vd)

    # 4. logo hãng -> src/logos.json
    # Thiếu bước này thì logos.json rỗng, và mọi khoảnh khắc "nói tới hãng
    # nào hiện logo hãng đó" im lặng biến mất -- đã sót đúng một lần.
    from pipeline.video import build_video as _bv
    from pipeline.video.models import Script as _S
    _script = _S.from_dict(json.loads(SCRIPT.read_text(encoding="utf-8")))
    got_logos = _bv._write_logos(_script, vd)
    log.info("logo: %d hãng -> %s", len(got_logos), sorted(got_logos))

    # 5. ảnh trang nguồn thật (bỏ qua trang chặn bot)
    got = sourceshot.capture_many(SOURCES, vd / "public/shots")
    (vd / "ref/shots.json").write_text(json.dumps(got, ensure_ascii=False, indent=1),
                                       encoding="utf-8")

    # 6. nhân vật: tách nền + viền, từ ảnh đặt tay trong portraits/
    text = " ".join(" ".join(c["lines"])
                    for c in json.loads(SCRIPT.read_text(encoding="utf-8"))["cards"])
    people = []
    for name in portrait.find_person_names(text):
        slug = name.lower().replace(" ", "-")
        r = portrait.fetch(name, vd / f"public/portraits/{slug}-cut.png",
                           extra_terms="Perplexity")
        if not r:
            log.warning("không có ảnh cho %s", name)
            continue
        people.append({
            "name": name, "file": f"portraits/{slug}-cut-red.png",
            "role": "Đồng sáng lập Perplexity", "credit": r["credit"],
            "date": "15 tháng 9, 2026", "masthead": "OpenAI Blog",
            "headline": "Họ kiểm tra AI ít hơn hẳn so với các thế hệ trước.",
            "standfirst": "Mỗi khi mô hình giỏi viết code hơn, công cụ tìm "
                          "kiếm lại thông minh hơn một bậc.",
        })
    (vd / "ref/people.json").write_text(json.dumps(people, ensure_ascii=False, indent=1),
                                        encoding="utf-8")

    # 7. khoảng lặng + căn chữ -> timeline.json
    dur = _align.make_silence_txt(vd / "public/voice.mp3", vd / "ref/silence.txt", video_dir=vd)
    r = subprocess.run(["node", "tools/align.mjs", str(dur)], cwd=vd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout.strip())
    if r.returncode != 0:
        log.error("align.mjs lỗi: %s", r.stderr[-600:])
        return 1

    log.info("xong -- %.2fs, %d ảnh nguồn, %d nhân vật", dur, len(got), len(people))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
