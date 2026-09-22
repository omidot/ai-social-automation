"""Chụp ảnh TRANG NGUỒN THẬT để chèn vào video.

Khác với screenshot.py (tìm bằng Google CSE rồi chụp trang đầu tiên), ở đây
ta đã có sẵn URL nguồn thật của bài — chụp thẳng, không cần khoá tìm kiếm.

Bài học đo được khi chụp 4 nguồn thật của một bản tin:
  - techcrunch.com  -> chụp được, dùng tốt
  - openai.com      -> Cloudflare chặn, ra trang "Verify you are human"
  - engadget.com    -> trả 403 "The request could not be satisfied"

Tức là quá nửa số nguồn KHÔNG chụp được. Việc bắt buộc phải có ở đây là
LOẠI BỎ những ảnh hỏng đó: một khung "Verify you are human" hay "403 ERROR"
lọt vào video đã xuất bản thì còn tệ hơn là không có ảnh nào.

Các trang chặn bot được bỏ qua, không tìm cách vượt qua.
"""
from __future__ import annotations
import logging
from pathlib import Path

log = logging.getLogger("video.sourceshot")


class SourceShotError(Exception):
    pass


# Dấu hiệu trang chặn bot / trang lỗi -- ảnh như vậy phải bị loại.
_BLOCKED_MARKERS = (
    "verify you are human", "are you a robot", "checking your browser",
    "enable javascript and cookies", "access denied", "403 error",
    "the request could not be satisfied", "request blocked",
    "attention required", "just a moment", "unusual traffic",
)

# Ẩn dải đồng ý cookie / quảng cáo bằng CSS thay vì bấm nút: bấm "Đồng ý" là
# thay mặt người dùng chấp nhận điều khoản, không được phép. Ẩn đi thì chỉ
# ảnh hưởng tới ảnh chụp, không gửi đồng ý nào cho trang.
#
# Đo thật trên một bản dựng: ảnh chụp techcrunch.com lọt vào video với một
# dải quảng cáo sự kiện màu tím ("Disrupt ticket savings...") và một khối
# "Advertisement" xám trống ngay giữa khung -- cả hai đều không khớp các mẫu
# cookie/consent/advert phía trên vì đó là banner sự kiện và khung quảng cáo
# hiển thị (display ad), không phải quảng cáo lập trình (programmatic ad).
# Thêm các mẫu chung cho thanh thông báo toàn trang / banner khuyến mãi /
# thanh điều hướng dính đầu trang.
_HIDE_CSS = """
  [id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i],
  [id*="gdpr" i], [class*="gdpr" i], [aria-label*="cookie" i],
  [class*="newsletter" i], [class*="paywall" i], [id*="onetrust" i],
  [class*="advert" i], [id*="advert" i], ins.adsbygoogle, iframe[src*="ads"],
  header, nav, [role="banner"], [role="navigation"],
  [class*="banner" i], [id*="banner" i],
  [class*="sitewide" i], [id*="sitewide" i],
  [class*="announcement" i], [id*="announcement" i],
  [class*="promo-bar" i], [class*="promobar" i], [class*="site-notice" i],
  [class*="sticky-header" i], [class*="ad-slot" i], [id*="ad-slot" i],
  [class*="dfp" i], [id*="dfp" i], [data-ad], [id^="google_ads_iframe"]
  { display: none !important; visibility: hidden !important; }
"""

# Nhãn văn bản của các khối quảng cáo hiển thị (không phải quảng cáo lập
# trình nên không có class/id rõ ràng) -- chỉ khớp được bằng nội dung chữ,
# CSS không làm được việc này nên xử lý riêng bằng JS.
_AD_LABELS = ("advertisement", "sponsored content", "sponsored", "quảng cáo")


def _looks_blocked(text: str) -> str | None:
    low = (text or "").lower()
    for m in _BLOCKED_MARKERS:
        if m in low:
            return m
    return None


def _is_mostly_blank(dest: Path) -> bool:
    """Ảnh gần như một màu = trang chưa dựng xong hoặc trang trắng."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return False
    with Image.open(dest) as im:
        a = np.asarray(im.convert("L").resize((160, 100)), dtype=float)
    # Độ lệch chuẩn thấp nghĩa là cả khung gần như đồng màu.
    return float(a.std()) < 12.0


def _hide_ad_labels(page) -> None:
    """Ẩn các khối quảng cáo hiển thị chỉ nhận ra được qua CHỮ ("Advertisement").

    Chỉ khớp phần tử lá có chữ NGẮN và TRÙNG KHỚP gần như toàn bộ -- tránh ẩn
    nhầm một đoạn văn thật chỉ vì trong câu có từ "sponsored".
    """
    page.evaluate("""(labels) => {
        const els = document.querySelectorAll('body *');
        for (const el of els) {
            if (el.children.length > 0) continue;
            const text = (el.innerText || '').trim().toLowerCase();
            if (text.length > 0 && text.length < 40 && labels.includes(text)) {
                let target = el;
                // Ẩn cả khung bọc ngoài (thường là ô trống rỗng chứa mỗi
                // nhãn này) nếu nó nhỏ, không phải cả một vùng lớn của trang.
                const parent = el.parentElement;
                if (parent && parent.getBoundingClientRect().height < 400) target = parent;
                target.style.setProperty('display', 'none', 'important');
            }
        }
    }""", list(_AD_LABELS))


def _scroll_to_article(page) -> None:
    """Cuộn xuống ĐẦU BÀI THẬT trước khi chụp.

    Mặc định chụp ở đầu trang -- đúng chỗ đặt thanh điều hướng, banner sự
    kiện, và ô quảng cáo lớn nhất trên hầu hết các trang tin. Cuộn heading
    hoặc khối bài viết đầu tiên vào khung nhìn thì ảnh chụp được mới là nội
    dung bài, không phải phần khung trang.
    """
    page.evaluate("""() => {
        const el = document.querySelector('article h1, article, h1, main');
        if (el) el.scrollIntoView({ block: 'start' });
    }""")
    page.wait_for_timeout(300)
    # Cuộn ngược lên một chút: scrollIntoView đặt heading sát mép trên cùng,
    # chừa vài chục pixel để không cắt mất dòng đầu.
    page.evaluate("window.scrollBy(0, -60)")


def capture(url: str, dest: Path, *, timeout_ms: int = 25000) -> None:
    """Chụp `url` vào `dest`. Ném SourceShotError nếu trang chặn hoặc ảnh rỗng."""
    from playwright.sync_api import sync_playwright

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1280, "height": 860},
            # User agent mặc định của Chromium headless bị nhiều trang chặn
            # thẳng; dùng chuỗi của một trình duyệt thật để trang trả về
            # đúng nội dung công khai mà người dùng thường vẫn thấy.
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
        )
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception:  # noqa: BLE001 -- trang chậm vẫn có thể đã dựng đủ
                pass
            page.wait_for_timeout(2500)

            body = ""
            try:
                body = page.inner_text("body", timeout=4000)[:4000]
            except Exception:  # noqa: BLE001
                pass
            hit = _looks_blocked(body)
            if hit:
                raise SourceShotError(f"trang chặn bot ({hit!r}): {url}")

            try:
                page.add_style_tag(content=_HIDE_CSS)
            except Exception:  # noqa: BLE001 -- ẩn được thì tốt, không thì thôi
                pass
            try:
                _hide_ad_labels(page)
            except Exception:  # noqa: BLE001
                pass
            try:
                _scroll_to_article(page)
            except Exception:  # noqa: BLE001 -- không cuộn được thì chụp nguyên đầu trang
                pass
            page.wait_for_timeout(400)
            page.screenshot(path=str(dest))
        finally:
            browser.close()

    if not dest.exists() or dest.stat().st_size == 0:
        raise SourceShotError(f"ảnh rỗng: {url}")
    if _is_mostly_blank(dest):
        dest.unlink(missing_ok=True)
        raise SourceShotError(f"ảnh gần như trắng trơn, bỏ: {url}")
    log.info("sourceshot: %s -> %s (%d KB)", url, dest, dest.stat().st_size // 1024)


def capture_many(urls: list[str], out_dir: Path, *, limit: int = 4) -> list[dict]:
    """Chụp lần lượt, bỏ qua trang hỏng. Trả về [{url, file}] những cái DÙNG ĐƯỢC.

    Không bao giờ ném lỗi: thiếu ảnh thì video vẫn phải dựng được.
    """
    out_dir = Path(out_dir)
    got: list[dict] = []
    for i, u in enumerate(urls):
        if len(got) >= limit:
            break
        dest = out_dir / f"src{i + 1}.png"
        try:
            capture(u, dest)
            got.append({"url": u, "file": f"shots/{dest.name}"})
        except Exception as e:  # noqa: BLE001 -- một nguồn hỏng không được làm hỏng video
            log.warning("sourceshot: bỏ %s (%s)", u, e)
    return got
