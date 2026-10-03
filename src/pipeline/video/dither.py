"""DITHER 1-BIT kiểu Bayer 8x8 -- nướng sẵn vào file PNG.

Phong cách video promo yêu cầu mọi hình ảnh (logo hãng, ảnh người, linh vật)
đều chỉ còn HAI MÀU, rung hạt theo ma trận Bayer 8x8. Việc này làm ở Python
chứ không phải bằng bộ lọc CSS lúc dựng hình -- đã có bài học đo được trong
chính repo này: chồng nhiều lớp filter lên ảnh lớn khiến Chromium treo hẳn,
một khung hình tĩnh chạy quá 10 phút không xong (xem portrait.py).

Nướng sẵn còn một cái lợi nữa: bản dựng trở thành tất định. Render lại lần
sau ra đúng từng pixel như bản snapshot người dùng đã duyệt.
"""
from __future__ import annotations
import logging
from pathlib import Path

log = logging.getLogger("video.dither")

# Ma trận ngưỡng Bayer 8x8 chuẩn, giá trị 0..63.
_BAYER_8 = (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def dither(src: Path, dest: Path, *, dark: str = "#141a22", light: str = "#fbf6e8",
           width: int | None = None, gamma: float = 1.0,
           keep_alpha: bool = True) -> Path:
    """Chuyển `src` thành ảnh 2 màu rung hạt Bayer 8x8, ghi ra `dest`.

    `dark`/`light` là đúng hai màu được phép xuất hiện. `keep_alpha` giữ nền
    trong suốt của ảnh đã tách nền (logo, linh vật) -- nếu bỏ, vùng trong
    suốt sẽ bị coi là sáng và biến thành mảng đặc màu `light`.
    """
    from PIL import Image

    src, dest = Path(src), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    im = Image.open(src).convert("RGBA")
    if width and im.width != width:
        h = round(im.height * width / im.width)
        im = im.resize((width, h), Image.LANCZOS)

    alpha = im.getchannel("A")
    grey = im.convert("L")
    if gamma != 1.0:
        lut = [min(255, round(255 * ((i / 255) ** gamma))) for i in range(256)]
        grey = grey.point(lut)

    w, h = grey.size
    gpx = grey.load()
    apx = alpha.load()

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    opx = out.load()
    dk, lt = _hex(dark), _hex(light)

    for y in range(h):
        row = _BAYER_8[y % 8]
        for x in range(w):
            if keep_alpha and apx[x, y] < 128:
                continue  # giữ trong suốt
            # Ngưỡng Bayer trải đều trên thang 0..255.
            thr = (row[x % 8] + 0.5) * (255.0 / 64.0)
            r, g, b = lt if gpx[x, y] > thr else dk
            opx[x, y] = (r, g, b, 255)

    out.save(dest)
    log.info("dither: %s -> %s (%dx%d)", src.name, dest.name, w, h)
    return dest


def dither_many(pairs: list[tuple[Path, Path]], **kw) -> list[Path]:
    """Nướng nhiều ảnh; một ảnh hỏng không được làm hỏng cả bản dựng."""
    done: list[Path] = []
    for s, d in pairs:
        try:
            done.append(dither(s, d, **kw))
        except Exception as e:  # noqa: BLE001
            log.warning("dither: bỏ %s (%s)", s, e)
    return done
