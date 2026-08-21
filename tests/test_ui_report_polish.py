"""UI polish — knowledge + security + report intelligence (item #A8-9).

User feedback (2026-05-09): "웹페이지 전체 ui 분위기를 사무적으로
지식과 보안을 갖춘 스마트한 보고서 관리 시스템이라는 점을 잘 나타날수
있게하는 디자인으로 개선".

Goals (subjective; tests assert presence not aesthetics):
  - Slate-tinted palette (cooler greys/blues for enterprise feel)
  - Logo gets a tagline that frames product as knowledge+security+report
  - James answer bubble feels like a "report card" (left accent rail
    + subtle box-shadow elevation)
  - Welcome screen reframes from generic "지식 추론 엔진" to
    "지식·보안·보고서 인텔리전스"
  - Top accent rail (1-2px gradient stripe) for system-header look

Run:
  python -m unittest tests.test_ui_report_polish
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "index.html"
# [v0.2.x #8] Page-specific styles also moved out of inline blocks
# into static/chat.css (chat) + static/admin.css (admin). Tests that
# read "HTML" to find CSS rules now consult both — the helpers below
# return the concatenated text so existing substring/regex
# assertions stay valid without per-test rewrites.
CHAT_CSS  = ROOT / "frontend" / "static" / "chat.css"
ADMIN_CSS = ROOT / "frontend" / "static" / "admin.css"
# Design tokens were extracted from inline :root blocks into a single
# stylesheet; palette assertions now resolve there instead of index.html.
TOKENS = ROOT / "frontend" / "static" / "tokens.css"


def _class_tokens(attrs: str) -> set[str]:
    """The class names in a raw attribute string, as a set.

    [2026-08-21] These modal assertions used to compare the literal
    `class="modal"`. The inline-style extraction rollout appends a
    generated utility class (`class="modal u-8f3a65ea"`), so an exact
    match started failing on markup that does carry the class. Compare
    tokens — that is what a browser does, and it survives the next
    utility class too.
    """
    m = re.search(r'class="([^"]*)"', attrs)
    return set(m.group(1).split()) if m else set()


def _chat_html_plus_css() -> str:
    return (HTML.read_text(encoding="utf-8")
            + "\n"
            + CHAT_CSS.read_text(encoding="utf-8"))


def _admin_html_plus_css(admin_path) -> str:
    return (admin_path.read_text(encoding="utf-8")
            + "\n"
            + ADMIN_CSS.read_text(encoding="utf-8"))


class PaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = TOKENS.read_text(encoding="utf-8")

    def test_brand_2_var_added(self):
        # Secondary brand colour for "intelligence cyan" — used by
        # status badges / dividers.
        self.assertIn("--brand-2:", self.tokens,
            "must declare --brand-2 secondary brand colour for the polish")
        self.assertIn("--brand-2-soft:", self.tokens,
            "soft variant for tinted backgrounds")

    def test_shadow_card_var_added(self):
        # Custom elevation token for "report card" surfaces.
        self.assertIn("--shadow-card:", self.tokens,
            "must declare --shadow-card token for elevation")
        m = re.search(r"--shadow-card:\s*([^;]+);", self.tokens, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertIn("rgba(0,0,0", m.group(1),
            "shadow should include a dark rgba layer")

    def test_palette_cooler_tones(self):
        # The base bg should be a tinted near-black (slate / cyber)
        # rather than pure black or the legacy neutral #0c0d10.
        # Post Task #22 mono migration lands on #04060a (deeper) —
        # earlier passes used #0a0c11. Both are acceptable here.
        m = re.search(r"--bg:\s*(#[0-9a-fA-F]{6})", self.tokens)
        self.assertIsNotNone(m)
        bg = m.group(1).lower()
        self.assertNotEqual(bg, "#000000",
            "pure black is too aggressive — keep slight tint")
        self.assertNotEqual(bg, "#0c0d10",
            "palette polish should refresh the bg tint")


class TopAccentRailTests(unittest.TestCase):
    """Top stripe was lifted from inline index.html style into tokens.css
    so admin/workspace/graph inherit the same rail. Assertions now resolve
    in the tokens file; index.html must NOT redeclare it."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = TOKENS.read_text(encoding="utf-8")
        cls.index_html = _chat_html_plus_css()

    def test_body_before_pseudo_present(self):
        # Subtle "system header" stripe at the top of every page.
        self.assertIn("body::before", self.tokens,
            "tokens.css must declare ::before stripe on body so all 4 "
            "pages inherit the system-header look")
        m = re.search(r"body::before\s*\{([^}]+)\}", self.tokens)
        self.assertIsNotNone(m)
        block = m.group(1)
        self.assertIn("position: fixed", block,
            "stripe must be fixed-position so it stays during scroll")
        self.assertIn("height", block)
        # Gradient between accent + brand-2.
        self.assertIn("linear-gradient", block,
            "stripe should use a gradient (accent → brand-2)")
        self.assertIn("var(--accent)", block)
        self.assertIn("var(--brand-2)", block)

    def test_stripe_is_thin(self):
        # Should be visually subtle — 1-3px tall, not a thick band.
        m = re.search(r"body::before\s*\{[^}]*height:\s*(\d+)px", self.tokens)
        self.assertIsNotNone(m, "couldn't extract stripe height")
        height = int(m.group(1))
        self.assertLessEqual(height, 4,
            f"stripe height {height}px too thick — must be ≤ 4px")

    def test_index_html_does_not_redeclare_rail(self):
        # Guard against drift back to inline declaration — the rule
        # belongs to tokens.css from now on.
        self.assertNotIn("body::before", self.index_html,
            "index.html must not redeclare body::before — it now lives "
            "in tokens.css for all 4 pages")


class LogoTaglineTests(unittest.TestCase):
    """The original brand framing lived in a single ``.tagline`` element.
    The brand refactor split it: the brand label carries the product
    name via ``class="brand"`` + ``class="brand-tail"`` (positioning
    line), and the knowledge/security/report framing lives in
    ``.welcome-sub`` (asserted by WelcomeReframeTests).

    [2026-08-21] Re-anchored. These asserted a ``<div class="logo">``
    header on the chat page. v0.6.1 (2026-06-15) restructured that page
    Claude-style: the header logo is gone, the short brand form
    ``SEKOS`` moved into ``.sidebar-header-brand``, and the full
    positioning phrase moved into the welcome hero. The *intent* —
    the brand label is the full positioning string, not a bare codename
    — is unchanged, so the assertions follow it to where it now lives
    rather than pinning the removed container. The other three pages
    keep their ``.logo`` header; CyberLiveIndicatorTests covers those.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = _chat_html_plus_css()

    def test_logo_uses_brand_class(self):
        # The brand label carries the unified .brand class, with the
        # .brand-tail span for the trailing positioning words.
        m = re.search(r'<span class="brand[^"]*">(.+?)</span>\s*</div>',
                      self.html, re.DOTALL)
        self.assertIsNotNone(m, "a .brand label must exist on the page")
        self.assertIn('class="brand', self.html,
            "the page must use the unified .brand class introduced "
            "with the positioning-line refactor")
        self.assertIn('class="brand-tail"', self.html,
            "brand must include the .brand-tail span for the trailing "
            "positioning words")

    def test_brand_positioning_line_present(self):
        # The brand label should be the full positioning string — not
        # just a codename. The trailing "Operating System" tail must sit
        # inside a .brand element so the compound reads as a system
        # identity. Since v0.6.1 that element is the welcome hero's.
        for m in re.finditer(r'<span class="brand[^"]*">(.+?)</span>\s*</div>',
                             self.html, re.DOTALL):
            if "Operating System" in m.group(1):
                self.assertIn("brand-tail", m.group(1),
                    "the positioning tail must be its own .brand-tail span")
                return
        self.fail("no .brand element carries the 'Operating System' "
                  "positioning tail")

    def test_sidebar_carries_the_short_brand_form(self):
        # v0.6.1 split the brand: short form in the sidebar header,
        # full positioning phrase in the hero. Pin the split so a
        # future edit does not silently drop one half.
        m = re.search(r'<div class="sidebar-title"[^>]*>(.+?)</div>',
                      self.html, re.DOTALL)
        self.assertIsNotNone(m, "sidebar title block must exist")
        self.assertIn("brand", m.group(1),
            "the sidebar brand mark must carry the .brand class")

    def test_logo_mark_uses_brand_2(self):
        # The square mark should blend accent → brand-2 for the
        # "intelligence" feel.
        m = re.search(r"\.logo::before\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m)
        block = m.group(1)
        self.assertIn("var(--brand-2)", block,
            "logo mark gradient should include the new brand-2 stop")


class ReportCardBubbleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _chat_html_plus_css()

    # [2026-08-21] Inverted, deliberately. These asserted a left accent
    # rail and a --shadow-card elevation on the assistant bubble. Both
    # were removed **per an operator catch** — chat.css records it in as
    # many words: "The left-accent rail / shadow / border were dropped
    # per operator catch — the bubble was visually crowding the reading
    # area on phones." The assistant reply now renders as bare body text
    # on the page background. Re-adding the rail to make a red test
    # green would re-introduce the thing the operator rejected, so these
    # pin the decision instead — a future edit that quietly restores the
    # bubble chrome fails here and has to argue with the catch.

    def test_james_bubble_has_no_chrome(self):
        m = re.search(r"\.msg\.james\s+\.bubble\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m, "couldn't locate james bubble rule")
        body = m.group(1)
        self.assertIn("background: transparent", body,
            "assistant reply renders on the page background, no bubble")
        self.assertIn("box-shadow: none", body,
            "the elevation was dropped per operator catch — do not "
            "restore it without re-opening that decision")
        self.assertNotIn("border-left", body,
            "the left accent rail was dropped per operator catch")

    def test_user_bubble_keeps_its_pill(self):
        # The reversal was scoped to the assistant side; the user
        # message keeps its right-aligned pill. Pin the asymmetry so a
        # cleanup does not flatten both.
        m = re.search(r"\.msg\.user\s+\.bubble\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m, "couldn't locate user bubble rule")
        body = m.group(1)
        self.assertIn("border-radius", body,
            "the user bubble is still a rounded pill")
        self.assertNotIn("background: transparent", body,
            "only the assistant side went chrome-less")


class WelcomeReframeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _chat_html_plus_css()

    def test_welcome_subtitle_mentions_security_and_reporting(self):
        # Old copy: "보안 중심 Graph-RAG 지식 추론 엔진".
        # New: 지식 + 보안 + 보고서 angle.
        m = re.search(
            r'<div class="welcome-sub">(.+?)</div>',
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m)
        sub = m.group(1)
        self.assertIn("보안", sub,
            "welcome subtitle must mention 보안")
        self.assertIn("보고서", sub,
            "welcome subtitle must mention 보고서 — the new framing")

    def test_welcome_has_english_descriptor(self):
        # Subtle uppercase English descriptor in mono — feels like an
        # enterprise product UI (e.g., "Knowledge · Security · Reporting").
        m = re.search(
            r'<div class="welcome-sub">(.+?)</div>',
            self.html, re.DOTALL,
        )
        sub = m.group(1)
        self.assertTrue(
            "Knowledge" in sub and "Security" in sub,
            "welcome should include an English descriptor mentioning "
            "Knowledge + Security for enterprise framing")


class CyberGlowTests(unittest.TestCase):
    """Cyber 6b — single-accent glow halos. tokens.css adds an
    always-on mint-cyan `box-shadow` to elements that fill with the
    accent (primary buttons, status badge). Disabled primary buttons
    must drop the glow so they don't read as active. Semantic
    `.btn-approve` / `.btn-reject` are intentionally untouched —
    green / red cues stay distinct from the mint halo."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = TOKENS.read_text(encoding="utf-8")

    def _block_after(self, marker: str) -> str:
        # Return the rule body that follows `marker` (a selector list)
        # up to the next closing brace.
        idx = self.tokens.find(marker)
        self.assertGreaterEqual(idx, 0, f"expected selector `{marker}`")
        close = self.tokens.find("}", idx)
        self.assertGreater(close, idx)
        return self.tokens[idx:close]

    def test_primary_buttons_get_strong_glow(self):
        # Selectors must list both .btn-primary (admin) and .send-btn
        # (index) so admin save / issue and chat send all halo.
        block = self._block_after(".btn-primary,")
        self.assertIn(".send-btn", block,
            "primary glow rule must list both .btn-primary and .send-btn")
        self.assertIn("box-shadow", block)
        # Mint-cyan rgba (107,231,208) at strong opacity (~.30 / .32).
        self.assertIn("rgba(107,231,208,.30)", block)
        self.assertIn("rgba(107,231,208,.32)", block)

    def test_disabled_primaries_drop_glow(self):
        # `:disabled` primaries must override to `box-shadow: none` —
        # otherwise a greyed-out send-btn would still halo as if active.
        block = self._block_after(".btn-primary:disabled,")
        self.assertIn(".send-btn:disabled", block,
            "disabled override must cover both primary classes")
        self.assertIn("box-shadow: none", block)

    def test_role_badge_gets_subtle_glow(self):
        # Login-state badge wraps in a soft ring. The inner .dot keeps
        # its grey / --success colour without an explicit halo.
        block = self._block_after(".role-badge {")
        self.assertIn("box-shadow", block,
            ".role-badge must carry the subtle perimeter glow")
        # Subtle ~.18 opacity, single 14px blur.
        self.assertIn("rgba(107,231,208,.18)", block)


class CyberGlassmorphismTests(unittest.TestCase):
    """Cyber 6c — `backdrop-filter: blur` on `.modal-overlay`
    (12px) + `.modal` / `.modal-card` (20px) with a mint inset glow
    on the modal box-shadow. Wrapped in `@supports` so unsupported
    engines fall back to the page-controlled solid overlay + card.

    Pages must declare semi-transparent overlay backgrounds (alpha
    ≤ .55) so the blur is visible — `rgba(0,0,0,.85)` styles would
    swallow the effect entirely."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = TOKENS.read_text(encoding="utf-8")

    def test_tokens_wraps_in_supports_guard(self):
        # `@supports` guard so engines without backdrop-filter don't
        # land in a half-applied state (overlay translucent but blur
        # absent).
        m = re.search(
            r"@supports\s*\(\(?\s*backdrop-filter:\s*blur",
            self.tokens,
        )
        self.assertIsNotNone(m,
            "6c block must be wrapped in @supports (backdrop-filter: blur(...))")

    def test_overlay_gets_12px_blur(self):
        # Overlay carries the lighter (12px) blur + saturate boost.
        m = re.search(
            r"\.modal-overlay\s*\{[^}]*backdrop-filter:\s*blur\(12px\)\s+saturate\(125%\)",
            self.tokens, re.DOTALL,
        )
        self.assertIsNotNone(m,
            ".modal-overlay must carry backdrop-filter: blur(12px) saturate(125%)")
        # Webkit prefix for Safari coverage.
        m = re.search(
            r"\.modal-overlay\s*\{[^}]*-webkit-backdrop-filter:\s*blur\(12px\)",
            self.tokens, re.DOTALL,
        )
        self.assertIsNotNone(m, "-webkit- prefix required for Safari")

    def test_modal_gets_20px_blur_and_mint_inset(self):
        # Modal cards carry the heavier (20px) blur and a 3-layer
        # box-shadow: mint inset + dark drop + mint outer halo.
        # The rule lists `.modal` and `.modal-card` together so graph
        # (which uses `.modal-card`) gets the same treatment.
        m = re.search(
            r"\.modal,\s*\.modal-card\s*\{([^}]+)\}",
            self.tokens, re.DOTALL,
        )
        self.assertIsNotNone(m,
            "expected combined `.modal, .modal-card` rule for 6c")
        block = m.group(1)
        self.assertIn("blur(20px)", block)
        self.assertIn("saturate(135%)", block)
        self.assertIn("-webkit-backdrop-filter", block)
        # Mint inset (1px) + dark drop + mint outer halo (28px).
        self.assertIn("rgba(107,231,208,.06) inset", block,
            "expected mint inset layer in the 3-layer box-shadow")
        self.assertIn("rgba(107,231,208,.12)", block,
            "expected mint outer halo layer in the 3-layer box-shadow")


class AdminModalClassExtractionTests(unittest.TestCase):
    """HANDOVER §8 follow-up — admin modal inner cards were lifted
    from inline `style="background:var(--surface);border:...;
    box-shadow:..."` into `class="modal"`. With the class in place,
    the cyber 6c glass treatment from tokens.css applies fully
    (backdrop-filter blur + mint 3-layer box-shadow), no longer
    just the overlay-side blur.

    Per-modal dimensions (width, padding, max-height, overflow)
    stay inline because the two modals differ — login is 340px,
    firstrun wizard is 560px and scrollable."""

    ADMIN = ROOT / "frontend" / "admin.html"

    @classmethod
    def setUpClass(cls):
        cls.html = _admin_html_plus_css(cls.ADMIN)

    def test_modal_class_rule_declared(self):
        # Admin must declare a base `.modal` rule so tokens.css 6c
        # has a surface to layer on. Bg must be translucent (alpha
        # ≤ .55) so the backdrop-filter blur is visible through it.
        m = re.search(r"\.modal\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m,
            "admin.html must declare `.modal` so the cyber 6c glass "
            "treatment applies to its modal inner cards")
        block = m.group(1)
        self.assertIn("rgba(7,9,14,.55)", block,
            "admin .modal bg must be the translucent surface "
            "(alpha .55) so backdrop-filter blur shows through")
        self.assertIn("border", block)
        self.assertIn("border-radius", block)

    def test_login_modal_uses_class(self):
        # The login modal inner card must carry `class="modal"` and
        # have shed the inline bg / border / box-shadow.
        m = re.search(
            r'id="admin-login-modal".+?<div\s+([^>]*)>',
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m, "admin-login-modal inner div must exist")
        inner = m.group(1)
        self.assertIn("modal", _class_tokens(inner),
            "admin-login-modal inner div must carry the `modal` class")
        # Bg / border / box-shadow must have moved out of inline style —
        # owned by the .modal rule + tokens.css 6c.
        self.assertNotIn("background:var(--surface)", inner,
            "inline `background:var(--surface)` must move to the "
            ".modal class rule")
        self.assertNotIn("box-shadow:", inner,
            "inline box-shadow must drop — tokens.css 6c owns it")

    def test_firstrun_modal_uses_class(self):
        m = re.search(
            r'id="firstrun-wizard-modal".+?<div\s+([^>]*)>',
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m,
            "firstrun-wizard-modal inner div must exist")
        inner = m.group(1)
        self.assertIn("modal", _class_tokens(inner),
            "firstrun-wizard-modal inner div must carry the `modal` class")
        self.assertNotIn("background:var(--surface)", inner,
            "inline `background:var(--surface)` must move to the "
            ".modal class rule")
        self.assertNotIn("box-shadow:", inner,
            "inline box-shadow must drop — tokens.css 6c owns it")
        # Per-modal customisation — firstrun is scrollable and wider
        # than the login modal. [2026-08-21] It used to live in the
        # inline style attribute; the inline-style extraction rollout
        # moved it into a generated utility class, so follow it into
        # the stylesheet instead of asserting it is still inline.
        util = [c for c in _class_tokens(inner) if c.startswith("u-")]
        self.assertTrue(util,
            "firstrun modal must carry its extracted utility class")
        css = TOKENS.read_text(encoding="utf-8")
        rule = re.search(r"\.%s\{([^}]*)\}" % re.escape(util[0]), css)
        self.assertIsNotNone(rule,
            f"utility class {util[0]} is referenced but never declared")
        decls = rule.group(1)
        self.assertIn("max-height:88vh", decls,
            "firstrun wizard remains scrollable (max-height + overflow)")
        self.assertIn("overflow-y:auto", decls)


class CyberLiveIndicatorTests(unittest.TestCase):
    """Cyber 6d — pulsing mint `.live-dot` + 1px scan line under
    active `.source-toggle button`. Animations are wrapped in
    `@media (prefers-reduced-motion: no-preference)` so reduced-
    motion users still see the static surfaces (dot + bottom line)
    without the pulse / sweep."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = TOKENS.read_text(encoding="utf-8")
        cls.index_html = _chat_html_plus_css()

    def test_keyframes_defined(self):
        # Both animations declared. Names are namespaced (`cyber-`)
        # so they don't collide with other keyframes the app might
        # ship later.
        self.assertIn("@keyframes cyber-pulse", self.tokens,
            "expected @keyframes cyber-pulse")
        self.assertIn("@keyframes cyber-scan", self.tokens,
            "expected @keyframes cyber-scan")

    def test_animations_gated_by_reduced_motion(self):
        # `animation:` properties must live inside
        # `@media (prefers-reduced-motion: no-preference)` so reduced-
        # motion users get the static dot + static bottom line.
        m = re.search(
            r"@media\s*\(\s*prefers-reduced-motion:\s*no-preference\s*\)\s*\{(.+?)\n\}",
            self.tokens, re.DOTALL,
        )
        self.assertIsNotNone(m,
            "6d animations must be wrapped in @media "
            "(prefers-reduced-motion: no-preference)")
        block = m.group(1)
        self.assertIn("animation: cyber-pulse", block,
            ".live-dot pulse animation must live inside the "
            "reduced-motion guard")
        self.assertIn("animation: cyber-scan", block,
            ".source-toggle scan animation must live inside the "
            "reduced-motion guard")

    def test_live_dot_static_styles_outside_guard(self):
        # Static dot styling (size, colour, shape) must apply even
        # under reduced motion — only the animation should drop.
        m = re.search(r"\.live-dot\s*\{([^}]+)\}", self.tokens)
        self.assertIsNotNone(m,
            "tokens.css must declare a base .live-dot rule outside "
            "the reduced-motion guard")
        block = m.group(1)
        self.assertIn("border-radius: 50%", block)
        self.assertIn("var(--accent)", block,
            "dot must paint with the mint accent")

    def test_scan_line_uses_accent_gradient(self):
        # The ::after carries a transparent → accent-fg → transparent
        # gradient so the streak shows over the soft-tinted active
        # button bg. accent-fg (a brighter mint shade) is used here
        # because plain --accent would blend into --accent-soft.
        m = re.search(
            r"\.source-toggle button\.active::after\s*\{([^}]+)\}",
            self.tokens,
        )
        self.assertIsNotNone(m,
            "tokens.css must declare the scan line ::after")
        block = m.group(1)
        self.assertIn("linear-gradient", block)
        self.assertIn("var(--accent-fg)", block,
            "scan line must use --accent-fg (brighter mint) so it "
            "shows over the --accent-soft active background")

    def test_active_toggle_uses_soft_tint(self):
        # The active source-toggle button background was migrated
        # from the solid `var(--accent)` fill to the soft-tinted
        # `var(--accent-soft)` so the scan line is visible.
        m = re.search(
            r"\.source-toggle button\.active\s*\{([^}]+)\}",
            self.index_html,
        )
        self.assertIsNotNone(m,
            "index.html must declare .source-toggle button.active rule")
        block = m.group(1)
        self.assertIn("var(--accent-soft)", block,
            "active toggle background must be --accent-soft (not solid "
            "--accent) so the scan line shows through")
        self.assertNotIn("color: #fff", block,
            "active toggle text colour must migrate from #fff to "
            "var(--accent) (mono-cyber outline+tint pattern)")

    # [2026-08-21] Scoped to the three pages that still have a `.logo`
    # header. v0.6.1 (2026-06-15) restructured the chat page
    # Claude-style and its header logo went with the redesign — and the
    # live-dot went with the logo, so index.html now carries no "system
    # live" cue at all. That is a real gap in the consistency this test
    # was written to protect, but closing it means adding markup to the
    # sidebar header, which is a UI decision and not a test fix. The
    # test below records the gap rather than asserting it away; see
    # test_chat_page_has_no_logo_header_by_design.

    def test_all_page_headers_have_live_dot(self):
        # The three console pages carry the live-dot inside `.logo` so
        # the "system live" cue is consistent across them. aria-hidden
        # because the dot is decorative — the system status it
        # represents isn't surfaced to screen readers from this element
        # alone.
        for name in ("admin.html", "workspace.html", "graph.html"):
            html = (ROOT / "frontend" / name).read_text(encoding="utf-8")
            m = re.search(r'<div class="logo">(.+?)</div>', html, re.DOTALL)
            self.assertIsNotNone(m, f"{name}: .logo block must exist")
            logo = m.group(1)
            self.assertRegex(logo, r'class="[^"]*\blive-dot\b',
                f"{name}: .logo must include the live-dot indicator")
            self.assertIn('aria-hidden', logo,
                f"{name}: live-dot must carry aria-hidden (decorative)")

    def test_chat_page_has_no_logo_header_by_design(self):
        # Pins the v0.6.1 restructure so the exclusion above stays
        # honest: if a `.logo` header ever returns to the chat page,
        # this fails and the live-dot loop should take index.html back.
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('<div class="logo">', html,
            "index.html grew a .logo header again — put it back into "
            "test_all_page_headers_have_live_dot and give it the dot")
        self.assertIn("sidebar-header-brand", html,
            "the chat page's brand mark lives in the sidebar header "
            "since v0.6.1")


class CyberBackgroundTextureTests(unittest.TestCase):
    """Cyber 6a — body background carries a mint-cyan grid + radial
    overlay so the four app surfaces share a subtle "system" backdrop.
    Layered as background-image on body in tokens.css. Pages must use
    `background-color: var(--bg)` (NOT the `background:` shorthand,
    which would reset background-image and erase the texture)."""

    PAGES = ("index.html", "admin.html", "workspace.html", "graph.html")

    # [v0.2.x #8] chat + admin have their CSS extracted to sibling
    # files; the body rule for those pages now lives there.
    # [PR-#8b, 2026-05-13] workspace + graph joined the extraction —
    # every page-level HTML now reads its body rule from a sibling
    # stylesheet.
    _EXTRACTED = {
        "index.html": "chat.css",
        "admin.html": "admin.css",
        "workspace.html": "workspace.css",
        "graph.html": "graph.css",
    }

    @classmethod
    def setUpClass(cls):
        cls.tokens = TOKENS.read_text(encoding="utf-8")
        def _read(name):
            html = (ROOT / "frontend" / name).read_text(encoding="utf-8")
            css_name = cls._EXTRACTED.get(name)
            if css_name:
                css = (ROOT / "frontend" / "static" / css_name
                       ).read_text(encoding="utf-8")
                return html + "\n" + css
            return html
        cls.pages = {name: _read(name) for name in cls.PAGES}

    def _body_block(self, css: str) -> str | None:
        # Match top-level `body { ... }` rules, skipping `body::before`
        # and other selectors. Returns the first body-only block found.
        for m in re.finditer(r"(^|\n)\s*body\s*\{([^}]+)\}", css):
            return m.group(2)
        return None

    def test_tokens_declares_cyber_texture(self):
        body = self._body_block(self.tokens)
        self.assertIsNotNone(body, "tokens.css must declare a body rule "
            "for the cyber 6a texture")
        self.assertIn("background-image", body,
            "body rule must carry a background-image with the 6a layers")
        # Mint-cyan rgba — same family as --accent #6be7d0.
        self.assertIn("rgba(107,231,208", body,
            "texture should use the mint-cyan accent (107,231,208)")
        # Two radial corner glows + two repeating-linear grids.
        self.assertGreaterEqual(body.count("radial-gradient("), 2,
            "expected two corner radial glows in the 6a texture")
        self.assertGreaterEqual(body.count("repeating-linear-gradient("), 2,
            "expected horizontal + vertical grid lines (2 layers)")
        self.assertIn("background-attachment: fixed", body,
            "texture must be viewport-anchored so it doesn't scroll")

    def test_pages_use_background_color_not_shorthand(self):
        # The `background:` shorthand resets background-image to none —
        # which would erase the texture layered in tokens.css. Each page
        # must use `background-color: var(--bg)` instead.
        for name, html in self.pages.items():
            body = self._body_block(html)
            self.assertIsNotNone(body, f"{name}: body rule must exist")
            self.assertNotRegex(body, r"\bbackground:\s*var\(--bg\)",
                f"{name}: body must use `background-color: var(--bg)` "
                "(the shorthand resets background-image and erases "
                "the cyber 6a texture from tokens.css)")
            self.assertIn("background-color: var(--bg)", body,
                f"{name}: body must declare `background-color: var(--bg)`")


if __name__ == "__main__":
    unittest.main()
