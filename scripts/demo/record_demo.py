"""
JAMES — automated demo recording script.

Records a 1~2 minute MP4 of the actual JAMES web UI in action:
  ① login → ② ask a real question → ③ answer with sources →
  ④ graph visualization → ⑤ admin panel (RBAC).

Runs both:
  - in this sandbox (against a tunnel URL exposing user's local server), and
  - directly on the user's PC (against http://localhost:8000).

Usage:
  pip install playwright && playwright install chromium
  JAMES_URL=https://xxx.trycloudflare.com \
  JAMES_USER=admin \
  JAMES_PW=<password> \
  python scripts/demo/record_demo.py

Output:
  scripts/demo/recordings/james-demo-<timestamp>.webm   (raw Playwright capture)
  scripts/demo/recordings/james-demo-<timestamp>.mp4    (if ffmpeg available)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout


URL = os.environ.get("JAMES_URL", "http://localhost:8000").rstrip("/")
USER = os.environ.get("JAMES_USER", "admin")
PW = os.environ.get("JAMES_PW", "")

DEMO_QUESTION = os.environ.get(
    "JAMES_DEMO_QUESTION",
    "이 시스템의 핵심 보안 원칙 3가지를 설명하고 출처를 보여주세요.",
)

OUT_DIR = Path(__file__).parent / "recordings"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime("%Y%m%d-%H%M%S")

VIEWPORT = {"width": 1440, "height": 900}


# ─── caption overlay (injected into page via JS) ────────────────────────────

CAPTION_CSS = """
#__demo_caption {
  position: fixed; left: 0; right: 0; bottom: 36px;
  display: flex; justify-content: center; pointer-events: none;
  z-index: 999999; font-family: 'Sora', 'Pretendard', sans-serif;
}
#__demo_caption > span {
  background: rgba(10, 10, 15, 0.92);
  color: #fff; padding: 14px 28px; border-radius: 10px;
  font-size: 22px; font-weight: 600; max-width: 80%;
  box-shadow: 0 6px 24px rgba(0,0,0,0.45);
  border: 1px solid rgba(124, 106, 247, 0.5);
  letter-spacing: 0.2px;
}
"""

CAPTION_JS = """
(text) => {
  let el = document.getElementById('__demo_caption');
  if (!el) {
    const style = document.createElement('style');
    style.textContent = `__CSS__`;
    document.head.appendChild(style);
    el = document.createElement('div');
    el.id = '__demo_caption';
    el.innerHTML = '<span></span>';
    document.body.appendChild(el);
  }
  el.querySelector('span').textContent = text;
  el.style.display = text ? 'flex' : 'none';
}
""".replace("__CSS__", CAPTION_CSS.replace("`", "\\`"))


async def caption(page: Page, text: str, hold_ms: int = 0):
    """Show a caption overlay; optionally hold for hold_ms before continuing."""
    await page.evaluate(CAPTION_JS, text)
    if hold_ms:
        await page.wait_for_timeout(hold_ms)


async def slow_type(page: Page, selector: str, text: str, delay_ms: int = 45):
    """Human-feeling typing (faster than default Playwright type)."""
    await page.click(selector)
    await page.fill(selector, "")
    await page.type(selector, text, delay=delay_ms)


# ─── scenario ───────────────────────────────────────────────────────────────


async def scene_intro(page: Page):
    await page.goto(URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(800)
    await caption(page, "JAMES — 사내 문서로 답하고, 그 답을 증명하는 AI", 2200)
    await caption(page, "")


async def scene_login(page: Page):
    if not PW:
        await caption(page, "[로그인 생략 — JAMES_PW 환경변수가 없습니다]", 1800)
        return
    await caption(page, "① 권한 검사 — 직원마다 볼 수 있는 범위가 다릅니다", 1500)
    await page.click("#role-badge")
    await page.wait_for_selector("#login-modal:not(.hidden)", timeout=4000)
    await slow_type(page, "#login-id", USER)
    await slow_type(page, "#login-pw", PW)
    await page.click("button.modal-btn.primary")
    # role badge updates after successful login
    try:
        await page.wait_for_function(
            "() => !document.getElementById('login-modal').classList.contains('hidden') === false",
            timeout=8000,
        )
    except PWTimeout:
        pass
    await page.wait_for_timeout(1200)
    await caption(page, f"  → '{USER}' 권한으로 로그인", 1500)
    await caption(page, "")


async def scene_ask(page: Page) -> bool:
    await caption(page, "② 사내 문서에 질문을 던집니다", 1600)
    await caption(page, "")
    await slow_type(page, "#chat-input", DEMO_QUESTION, delay_ms=40)
    await page.wait_for_timeout(600)
    await page.click("#send-btn")
    await caption(page, "③ 검색 → 그래프 → LLM 추론 진행 중…", 0)

    # Wait for answer — up to 90s for slow local LLMs.
    initial_count = await page.locator("#messages > div").count()
    deadline = 90
    interval = 1
    waited = 0
    while waited < deadline:
        await page.wait_for_timeout(interval * 1000)
        waited += interval
        try:
            current = await page.locator("#messages > div").count()
            if current > initial_count:
                # let final tokens stream in
                await page.wait_for_timeout(2500)
                await caption(page, "")
                return True
        except Exception:
            pass
    await caption(page, "[답변 timeout — LLM 응답이 늦어집니다]", 2000)
    return False


async def scene_show_answer(page: Page):
    await caption(page, "④ 답변 + 출처 문서 + 추론 경로", 2200)
    # scroll messages to bottom
    await page.evaluate(
        "() => { const m = document.getElementById('messages'); if (m) m.scrollTop = m.scrollHeight; }"
    )
    await page.wait_for_timeout(2500)
    await caption(page, "    모든 답에 출처가 따라옵니다 — 감사 가능", 2200)
    await caption(page, "")


async def scene_graph(page: Page):
    await caption(page, "⑤ 그래프 시각화 — '왜 이 답?' 추론 경로", 1400)
    await page.goto(f"{URL}/graph", wait_until="domcontentloaded")
    await page.wait_for_timeout(3500)  # let graph render
    # wiggle the canvas for a bit of motion
    try:
        canvas = page.locator("#graph-canvas")
        box = await canvas.bounding_box()
        if box:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            for dx, dy in [(60, 30), (-90, -20), (40, -60), (0, 0)]:
                await page.mouse.move(cx + dx, cy + dy, steps=20)
                await page.wait_for_timeout(400)
    except Exception:
        pass
    await caption(page, "    엔티티 사이 관계가 답의 근거로 연결됨", 2200)
    await caption(page, "")


async def scene_admin(page: Page):
    await caption(page, "⑥ 어드민 — RBAC, 감사 로그, 정책 엔진", 1400)
    await page.goto(f"{URL}/admin", wait_until="domcontentloaded")
    await page.wait_for_timeout(3500)
    await caption(page, "    누가 / 언제 / 무엇을 / 왜 — append-only 로그", 2400)
    await caption(page, "")


async def scene_outro(page: Page):
    await page.goto(URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(800)
    await caption(
        page,
        "외부 호출 0회. 모든 답에 근거. 권한은 검색 단계부터.",
        3000,
    )
    await caption(page, "JAMES v0.2 — PoC 파트너 모집 중", 2500)


# ─── runner ─────────────────────────────────────────────────────────────────


async def main():
    print(f"[demo] target URL: {URL}")
    print(f"[demo] user: {USER!r}, pw: {'set' if PW else '<empty>'}")
    print(f"[demo] question: {DEMO_QUESTION!r}")
    print(f"[demo] output dir: {OUT_DIR}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(OUT_DIR),
            record_video_size=VIEWPORT,
            ignore_https_errors=True,
        )
        page = await context.new_page()

        try:
            await scene_intro(page)
            await scene_login(page)
            ok = await scene_ask(page)
            if ok:
                await scene_show_answer(page)
            await scene_graph(page)
            await scene_admin(page)
            await scene_outro(page)
        except Exception as e:
            print(f"[demo] scene error: {e!r}", file=sys.stderr)
            await caption(page, f"[error] {e}", 2500)

        await page.wait_for_timeout(500)
        # Playwright writes the video on context.close()
        await context.close()
        await browser.close()

    # Find the freshly written .webm and rename / convert
    webms = sorted(OUT_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not webms:
        print("[demo] no video produced", file=sys.stderr)
        return 1
    raw = webms[-1]
    final_webm = OUT_DIR / f"james-demo-{TS}.webm"
    raw.rename(final_webm)
    print(f"[demo] webm: {final_webm}")

    if shutil.which("ffmpeg"):
        final_mp4 = OUT_DIR / f"james-demo-{TS}.mp4"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(final_webm),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-vf", "scale=1440:900",
            str(final_mp4),
        ]
        subprocess.run(cmd, check=False)
        if final_mp4.exists():
            print(f"[demo] mp4:  {final_mp4}")
    else:
        print("[demo] ffmpeg not on PATH — skipping mp4 conversion (webm is usable)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
