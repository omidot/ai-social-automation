"""Ảnh NHÂN VẬT: tìm, tải, tách nền, viền trắng.

Khi bài nhắc tới một người cụ thể ("Johnny Ho, đồng sáng lập Perplexity"),
video nên cho thấy mặt người đó thay vì để khung chữ trơn. Module này lo
phần nặng: tìm ảnh, tách nền bằng rembg, rồi viền trắng quanh hình đã tách
để nó nổi lên trên nền tối.

Ràng buộc phải nhớ:
  - Chỉ dùng cho NGƯỜI CỦA CÔNG CHÚNG được bài báo nhắc đích danh, đúng
    kiểu bản tin vẫn làm. Không dùng cho người thường.
  - Ảnh tải về là ảnh của người thật; nguồn được ghi lại kèm để video có
    thể hiện dòng ghi công.
  - Mọi bước đều có thể hỏng (không có khoá tìm kiếm, tải lỗi, tách nền
    lỗi). Hỏng thì trả None và video dựng tiếp bình thường -- không bao giờ
    làm sập cả bản dựng vì một tấm ảnh.
"""
from __future__ import annotations
import io
import logging
import re
from pathlib import Path

import httpx

log = logging.getLogger("video.portrait")

_SEARCH = "https://www.googleapis.com/customsearch/v1"

# Viền trắng quanh hình đã tách -- độ dày tính theo pixel ở cỡ ảnh chuẩn hoá.
_OUTLINE_PX = 9
# Cỡ chuẩn hoá trước khi viền, để viền dày đều bất kể ảnh gốc to nhỏ.
_TARGET_H = 1100


class PortraitError(Exception):
    pass


def find_person_names(text: str) -> list[str]:
    """Tên người xuất hiện trong kịch bản.

    Nhận diện bằng dấu hiệu tiếng Việt quen thuộc của bản tin: một cụm 2-3
    từ VIẾT HOA đứng ngay trước hoặc sau một chức danh. Chỉ dựa vào chữ hoa
    thôi thì dính cả tên công ty và tên sản phẩm.
    """
    roles = ("đồng sáng lập", "nhà sáng lập", "sáng lập", "CEO", "giám đốc",
             "chủ tịch", "trưởng nhóm", "kỹ sư trưởng", "phó chủ tịch")
    cap = r"[A-ZÀ-Ỹ][\wÀ-ỹ]+(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ]+){1,2}"
    out: list[str] = []
    for role in roles:
        for pat in (rf"{cap}(?=\s*,?\s*{re.escape(role)})",
                    rf"(?<={re.escape(role)})\s+({cap})"):
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                name = (m.group(1) if m.groups() else m.group(0)).strip(" ,.")
                if name and name not in out:
                    out.append(name)
    return out


_WIKI = "https://en.wikipedia.org/w/api.php"
_UA = "AHitOfficial/1.0 (https://github.com/omidot/ai-social-automation)"


def wikipedia_image(name: str, timeout: int = 15) -> tuple[str, str] | None:
    """Ảnh chân dung trên Wikipedia, kèm tên trang để ghi nguồn.

    Ưu tiên nguồn này hơn tìm ảnh bằng Google: ảnh trên Wikimedia có giấy
    phép rõ ràng và tra được, còn kết quả tìm ảnh thường là ảnh có bản
    quyền không rõ nguồn. Đổi lại, chỉ người đủ nổi tiếng mới có trang --
    không có thì trả None và video bỏ qua phần nhân vật.
    """
    try:
        r = httpx.get(_WIKI, params={
            "action": "query", "format": "json", "prop": "pageimages",
            "piprop": "original", "titles": name, "redirects": 1,
        }, timeout=timeout, headers={"User-Agent": _UA})
        pages = ((r.json() or {}).get("query") or {}).get("pages") or {}
        for pg in pages.values():
            src = (pg.get("original") or {}).get("source")
            if src:
                return pg.get("title", name), src
    except Exception as e:  # noqa: BLE001
        log.warning("portrait: tra Wikipedia lỗi cho %r (%s)", name, e)
    return None


def _search_image(query: str, *, api_key: str, cx: str, timeout: int = 10) -> str:
    r = httpx.get(_SEARCH, params={
        "key": api_key, "cx": cx, "q": query,
        "searchType": "image", "num": 5, "imgSize": "large", "safe": "active",
    }, timeout=timeout)
    if r.status_code != 200:
        raise PortraitError(f"tìm ảnh HTTP {r.status_code}")
    items = (r.json() or {}).get("items") or []
    for it in items:
        link = it.get("link") or ""
        if link.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
            return link
    raise PortraitError(f"không có ảnh hợp lệ cho {query!r}")


def _cutout(raw: bytes) -> "object":
    """Tách nền, chuẩn hoá cỡ, cắt sát mép người."""
    from PIL import Image
    from rembg import remove

    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    cut = remove(im)
    box = cut.getbbox()
    if box:
        cut = cut.crop(box)
    if cut.height > _TARGET_H:
        w = round(cut.width * _TARGET_H / cut.height)
        cut = cut.resize((w, _TARGET_H), Image.LANCZOS)
    return cut


def _outline(im: "object", px: int = _OUTLINE_PX) -> "object":
    """Viền trắng quanh hình đã tách, để nó bật lên trên nền tối."""
    from PIL import Image, ImageFilter

    pad = px * 2
    base = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    base.paste(im, (pad, pad), im)

    alpha = base.split()[3]
    # Nở vùng đặc rồi tô trắng -> thành viền bao quanh.
    grown = alpha.filter(ImageFilter.MaxFilter(px * 2 + 1))
    ring = Image.new("RGBA", base.size, (255, 255, 255, 255))
    ring.putalpha(grown)
    ring.alpha_composite(base)
    return ring


def fetch(name: str, out_path: Path, *, api_key: str = "", cx: str = "",
          extra_terms: str = "") -> dict | None:
    """Tìm -> tải -> tách nền -> viền trắng. Trả về {file, source} hoặc None.

    Thứ tự nguồn: Wikipedia trước (giấy phép rõ ràng), chỉ khi không có mới
    dùng tới tìm ảnh bằng khoá -- và nếu không có khoá thì dừng hẳn, không
    đi vơ ảnh ở nguồn không rõ bản quyền.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    query = f"{name} {extra_terms}".strip()
    credit = ""
    try:
        hit = wikipedia_image(name)
        if hit:
            credit, url = f"Wikipedia · {hit[0]}", hit[1]
        elif api_key and cx:
            url = _search_image(query, api_key=api_key, cx=cx)
        else:
            raise PortraitError("không có ảnh giấy phép rõ ràng cho người này")
        # Wikimedia từ chối User-Agent chung chung ("Mozilla/5.0" -> 403);
        # chính sách của họ đòi UA nêu rõ ứng dụng và cách liên hệ.
        r = httpx.get(url, timeout=20, follow_redirects=True,
                      headers={"User-Agent": _UA})
        if r.status_code != 200 or not r.content:
            raise PortraitError(f"tải ảnh HTTP {r.status_code}")
        cut = _cutout(r.content)
        if cut.width < 120 or cut.height < 160:
            raise PortraitError("hình tách ra quá nhỏ, có lẽ tách hỏng")
        _outline(cut).save(out_path, format="PNG")
    except Exception as e:  # noqa: BLE001 -- một tấm ảnh hỏng không được làm sập bản dựng
        log.warning("portrait: bỏ %r (%s)", name, e)
        return None
    log.info("portrait: %s -> %s", name, out_path)
    return {"file": out_path.name, "name": name, "source": url, "credit": credit}
