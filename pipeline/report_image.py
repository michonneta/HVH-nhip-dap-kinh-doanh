"""Chụp toàn bộ Bản tin HTML thành ảnh JPEG để gửi vào Lark (trình duyệt Chromium không giao diện qua Playwright).

Playwright chỉ cài khi cần chụp ảnh (lượt gửi bản tin), để các lượt chạy định kỳ 30 phút không tốn thời gian cài.
"""
import logging
import subprocess
import sys

log = logging.getLogger("nhip-dap")
WIDTH = 1000          # khung nhìn; trang báo cáo rộng 940px
MAX_HEIGHT_PX = 11000  # giới hạn chiều cao ảnh (Lark giới hạn kích thước ảnh); vượt thì giảm độ nét
SCALE = 1.5


def _ensure_playwright():
    try:
        import playwright  # noqa: F401
    except ImportError:
        log.info("Cài Playwright…")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright==1.48.0"], check=True)
    # tải Chromium và thư viện hệ thống (đã có thì bỏ qua nhanh)
    subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=True,
                   capture_output=True)


def render_jpeg(html: str) -> bytes:
    _ensure_playwright()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # lần 1: đo chiều cao trang để chọn độ nét sao cho ảnh không vượt giới hạn
            probe = browser.new_page(viewport={"width": WIDTH, "height": 1200})
            probe.set_content(html, wait_until="load")
            height = probe.evaluate("document.querySelector('main.page').getBoundingClientRect().height")
            probe.close()
            scale = min(SCALE, MAX_HEIGHT_PX / max(height, 1))
            page = browser.new_context(viewport={"width": WIDTH, "height": 1200}, device_scale_factor=scale).new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_content(html, wait_until="load")
            img = page.locator("main.page").screenshot(type="jpeg", quality=85)
            if errors:
                log.warning("Lỗi JavaScript khi dựng bản tin: %s", errors[:3])
            log.info("Ảnh bản tin: %.0f px cao, %.1f MB", height * scale, len(img) / 1e6)
            return img
        finally:
            browser.close()
