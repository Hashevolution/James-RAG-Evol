#!/usr/bin/env python3
"""Generate the PROJECT JAMES architecture infographic as a self-contained SVG.

Two locales are produced: English (``en``) and Korean (``ko``). The layout is a
multi-panel poster (header + feature chips + comparison + 3-column architecture +
state & knowledge + how-it-works flow + capabilities/why-special + verified
numbers) modelled after a LinkedIn-style "agent architecture" infographic, but
filled entirely from JAMES's real code / docs / roadmap.

The SVG references system fonts by name (Inter / Noto Sans KR with sans-serif
fallbacks) so it renders crisply in any browser or vector tool without bundling
font binaries. No third-party Python deps required.

Usage:
    python reports/promo-assets/infographic/generate_infographic.py
    # writes james_architecture_en.svg and james_architecture_ko.svg next to it
"""
from __future__ import annotations

import html
import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Geometry / theme
# ---------------------------------------------------------------------------
W = 1640
PAD = 56            # outer page padding
INNER = W - 2 * PAD  # 1528
GAP = 24            # gap between side-by-side panels
SEC_GAP = 34        # vertical gap between stacked sections
PANEL_PAD = 18
HEADER_H = 40
HEAD_GAP = 12

BG = "#F8FAFC"
INK = "#0F172A"
SUB = "#475569"
BODY = "#334155"
STROKE = "#E2E8F0"

# palette: (background, foreground)
PAL = {
    "indigo": ("#EEF2FF", "#4338CA"),
    "blue":   ("#EFF6FF", "#1D4ED8"),
    "green":  ("#ECFDF5", "#047857"),
    "amber":  ("#FEF3C7", "#B45309"),
    "purple": ("#F5F3FF", "#6D28D9"),
    "red":    ("#FEF2F2", "#B91C1C"),
    "orange": ("#FFF7ED", "#C2410C"),
}

FONT_EN = "Inter, 'Helvetica Neue', Arial, sans-serif"
FONT_KO = ("'Noto Sans CJK KR', 'Noto Sans KR', 'Apple SD Gothic Neo', "
           "'Malgun Gothic', 'Nanum Gothic', sans-serif")


# ---------------------------------------------------------------------------
# Text measuring + wrapping (approximate, intentionally over-estimates width
# so lines wrap early and never overflow horizontally).
# ---------------------------------------------------------------------------
def _char_w(ch: str, size: float) -> float:
    o = ord(ch)
    if ch == " ":
        return size * 0.30
    if o > 0x1100:  # CJK / Hangul ~ full width
        return size * 1.04
    if ch in "ilIj.,:;'!|":
        return size * 0.32
    if ch in "mwMW@":
        return size * 0.82
    if ch.isupper():
        return size * 0.64
    return size * 0.56


def text_w(s: str, size: float) -> float:
    return sum(_char_w(c, size) for c in s)


def wrap(s: str, maxw: float, size: float) -> list[str]:
    out: list[str] = []
    for para in s.split("\n"):
        words = para.split(" ")
        line = ""
        for wd in words:
            cand = wd if not line else line + " " + wd
            if text_w(cand, size) <= maxw or not line:
                line = cand
            else:
                out.append(line)
                line = wd
        out.append(line)
    return out


# ---------------------------------------------------------------------------
# SVG primitives
# ---------------------------------------------------------------------------
def esc(s: str) -> str:
    return html.escape(s, quote=True)


def rect(x, y, w, h, fill, rx=12, stroke=None, sw=1.0) -> str:
    s = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{sw}"'
    return s + "/>"


def tspan(x, y, s, size, weight, color, anchor="start", spacing=None) -> str:
    ls = f' letter-spacing="{spacing}"' if spacing is not None else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}" text-anchor="{anchor}"{ls}>{esc(s)}</text>')


@dataclass
class Block:
    w: float
    h: float
    svg: str  # local coords starting at (0,0)


def g(x, y, svg) -> str:
    return f'<g transform="translate({x:.1f},{y:.1f})">{svg}</g>'


# ---------------------------------------------------------------------------
# Composite builders (all return Block in local coords)
# ---------------------------------------------------------------------------
def lines_block(x, lines, size, weight, color, lh, y0) -> tuple[str, float]:
    out, y = [], y0
    for ln in lines:
        y += size
        out.append(tspan(x, y, ln, size, weight, color))
        y += size * (lh - 1)
    return "".join(out), y


def card(w, title, desc, key, *, tsize=15, dsize=13, pad=14, forced_h=None) -> Block:
    bg, fg = PAL[key]
    tl = wrap(title, w - 2 * pad, tsize)
    dl = wrap(desc, w - 2 * pad, dsize) if desc else []
    body, y = lines_block(pad, tl, tsize, "700", fg, 1.2, pad)
    if dl:
        y += 4
        d, y = lines_block(pad, dl, dsize, "400", SUB, 1.32, y)
        body += d
    y += pad
    h = forced_h if forced_h else y
    return Block(w, h, rect(0, 0, w, h, bg, 12) + body)


def node(w, title, sub, key, *, forced_h=None) -> Block:
    bg, fg = PAL[key]
    pad = 11
    tl = wrap(title, w - 2 * pad, 14)
    sl = wrap(sub, w - 2 * pad, 12) if sub else []
    body, y = lines_block(pad, tl, 14, "700", fg, 1.2, pad)
    if sl:
        y += 2
        d, y = lines_block(pad, sl, 12, "400", SUB, 1.3, y)
        body += d
    y += pad
    h = forced_h if forced_h else y
    return Block(w, h, rect(0, 0, w, h, bg, 10, stroke=fg, sw=1.0) + body)


def number_card(w, num, label, fg, *, forced_h=None) -> Block:
    pad = 14
    ll = wrap(label, w - 2 * pad, 12.5)
    body = tspan(pad, pad + 30, num, 32, "800", fg)
    _, y = (body, pad + 30)
    d, y = lines_block(pad, ll, 12.5, "400", SUB, 1.3, pad + 38)
    h = forced_h if forced_h else y + pad
    return Block(w, h, rect(0, 0, w, h, "#F1F5F9", 12) + body + d)


def flow(items: list[Block], cw: float, gap: float, *, uniform=True) -> Block:
    if uniform and items:
        mh = max(b.h for b in items)
        items = [Block(b.w, mh, _resize_bg(b.svg, b.w, mh)) for b in items]
    x = y = rowh = 0.0
    out = []
    for b in items:
        if x > 0 and x + b.w > cw + 0.5:
            x = 0
            y += rowh + gap
            rowh = 0
        out.append(g(x, y, b.svg))
        x += b.w + gap
        rowh = max(rowh, b.h)
    return Block(cw, y + rowh, "".join(out))


def _resize_bg(svg: str, w: float, h: float) -> str:
    # replace the first rect's height (cards start with their bg rect at 0,0)
    import re
    return re.sub(r'(<rect x="0.0" y="0.0" width="[\d.]+" height=")[\d.]+(")',
                  lambda m: f'{m.group(1)}{h:.1f}{m.group(2)}', svg, count=1)


def bullets(w, items, fg, *, size=13) -> Block:
    pad = 0
    y = 0.0
    out = []
    for it in items:
        ll = wrap(it, w - 18, size)
        cy = y + size
        out.append(f'<circle cx="3.5" cy="{cy - size*0.32:.1f}" r="3.5" fill="{fg}"/>')
        for i, ln in enumerate(ll):
            yy = y + size + i * size * 1.36
            out.append(tspan(16, yy, ln, size, "400", BODY))
        y += size + (len(ll) - 1) * size * 1.36 + 10
    return Block(w, y, "".join(out))


def step_card(w, num, title, desc, key) -> Block:
    bg, fg = PAL[key]
    pad = 14
    tl = wrap(title, w - 2 * pad, 14)
    dl = wrap(desc, w - 2 * pad, 12)
    badge = (f'<circle cx="{pad+14}" cy="{pad+14}" r="14" fill="{fg}"/>'
             f'<text x="{pad+14}" y="{pad+19}" font-size="14" font-weight="800" '
             f'fill="#FFFFFF" text-anchor="middle">{num}</text>')
    body, y = lines_block(pad, tl, 14, "700", INK, 1.2, pad + 36)
    y += 2
    d, y = lines_block(pad, dl, 12, "400", SUB, 1.32, y)
    y += pad
    return Block(w, y, rect(0, 0, w, y, bg, 12) + badge + body + d)


def panel_total(content: Block) -> float:
    return PANEL_PAD + HEADER_H + HEAD_GAP + content.h + PANEL_PAD


def panel(x, y, w, title, key, content: Block, *, header_fg=None, header_bg=None,
          forced_total=None) -> tuple[str, float]:
    bg, fg = PAL[key]
    hbg = header_bg or bg
    hfg = header_fg or fg
    total = panel_total(content)
    if forced_total and forced_total > total:
        total = forced_total
    out = [rect(x, y, w, total, "#FFFFFF", 16, stroke=STROKE, sw=1.0)]
    hx, hy = x + PANEL_PAD, y + PANEL_PAD
    out.append(rect(hx, hy, w - 2 * PANEL_PAD, HEADER_H, hbg, 8))
    out.append(tspan(hx + 14, hy + 26, title, 16, "800", hfg))
    out.append(g(x + PANEL_PAD, y + PANEL_PAD + HEADER_H + HEAD_GAP, content.svg))
    return "".join(out), total


def band(x, y, w, title) -> tuple[str, float]:
    h = 44
    out = rect(x, y, w, h, "#4338CA", 8) + tspan(x + 16, y + 29, title, 17, "800", "#FFFFFF")
    return out, h


# ---------------------------------------------------------------------------
# Locale content
# ---------------------------------------------------------------------------
def content(lang: str) -> dict:
    if lang == "en":
        return dict(
            font=FONT_EN,
            tags="#GraphRAG    #ReplayableRAG    #AuditableAI    #LocalFirst",
            title="PROJECT JAMES",
            subtitle="A local-first, auditable knowledge-reasoning platform — Graph-RAG "
                     "retrieval, deterministic contradiction arbitration, and "
                     "byte-identical replayable state.",
            badges=[("v0.4.1 · T6 Causality Chain", "indigo"), ("MIT License", "green"),
                    ("Python 3.11+", "blue"), ("3290 tests · all green", "amber"),
                    ("DOI 10.5281/zenodo.20426719", "purple"),
                    ("Mother platform → v1.0", "red")],
            love_h="WHY DEVELOPERS LOVE JAMES",
            love=[("Local-first", "Runs fully on-prem; no data leaves the box by default.", "green"),
                  ("Replayable RAG", "reconstruct_view_at() rebuilds any past state byte-identically.", "indigo"),
                  ("Append-only audit", "Every decision logged immutably — full provenance.", "blue"),
                  ("Deterministic arbiter", "LLM-free 4-rule contradiction tree, replay-safe.", "amber"),
                  ("Plugin API", "Typed module boundaries; extend without forking core.", "purple"),
                  ("Default-OFF invariant", "New routing layers ship OFF — byte-identical until opt-in.", "red")],
            vs_h="WHY JAMES ≠ FLAT / CLOUD RAG",
            vs=["Replayable: past state reconstructed exactly, not approximated.",
                "Deterministic contradiction arbitration vs prompt-only heuristics.",
                "Explicit Trust Zones isolate low-trust input before the LLM.",
                "On-prem ownership + correction moat — no vendor lock-in.",
                "Cloud egress gated by an abstraction trust contract."],
            arch_h="JAMES ARCHITECTURE OVERVIEW",
            entry_h="ENTRY POINTS",
            entry=[("Frontend / API", "UI + REST surface"),
                   ("Auth + PolicyEngine", "RBAC / ABAC · single policy source"),
                   ("Query Router", "intent classify · scope routing")],
            core_h="JAMES CORE",
            core=[("Hybrid Retrieval", "vector + BM25 · rerank"),
                  ("Graph Engine", "Graph-RAG · typed paths"),
                  ("Cognitive Middleware", "auto-router · adaptive budget · entity-anchor · query-rewrite"),
                  ("Reasoning Loop", "plan → retrieve → verify → synth"),
                  ("Trust-gated Memory", "episodic · working · loom")],
            exec_h="EXECUTION SURFACES",
            exec=[("Tool Router", "FS / Web sandbox · allowlist"),
                  ("Cloud Egress Zone", "abstraction module · mask + audit"),
                  ("Wiki Generator", "auditable knowledge pages"),
                  ("Output Filter", "PII + role mask")],
            state_h="STATE & KNOWLEDGE",
            state=[("Layer 4 Lifecycle", "T1 temporal · T7 supersede · T2 contradiction · T6 causality", "amber"),
                   ("Knowledge Cascade (L3)", "delete / modify propagation across derived facts", "red"),
                   ("Ontology + Typed Filter", "relation schema · entity-typed graph filtering", "indigo"),
                   ("Graph Snapshot / Replay", "reconstruct_view_at — 'what was true at T?'", "green"),
                   ("Append-only Audit Log", "every state change immutable + replayable", "blue")],
            how_h="HOW JAMES WORKS",
            how=[("1", "Route", "Query classified; scope + budget decided.", "blue"),
                 ("2", "Retrieve", "Hybrid vector+BM25 retrieval, reranked.", "indigo"),
                 ("3", "Traverse", "Graph engine walks typed paths for evidence.", "purple"),
                 ("4", "Reason", "Loop plans, verifies, synthesizes ↔ memory.", "amber"),
                 ("5", "Arbitrate", "Deterministic 4-rule contradiction tree.", "red"),
                 ("6", "Mask", "Output filtered for PII + role.", "orange"),
                 ("7", "Audit", "Append-only log records every decision.", "green")],
            cap_h="PLATFORM CAPABILITIES (mother platform → v1.0)",
            cap=["Auditable Graph-RAG over private corpora with full provenance.",
                 "Time-travel queries — reconstruct knowledge as of any past point.",
                 "Self-evolution with a mandatory human approval gate (opt-in only).",
                 "Hybrid cloud reasoning tier behind an abstraction trust contract.",
                 "v0.5 candidate: enterprise internal-knowledge ontology (gated)."],
            spc_h="WHY JAMES IS SPECIAL",
            spc=["Replayable RAG — byte-identical historical state, by construction.",
                 "Deterministic contradiction arbitration — no LLM in the decision path.",
                 "Trust Zones gate every low-trust source before the LLM context.",
                 "Human approval gate on self-evolution — never silent auto-deploy.",
                 "Reproducible & cited — every headline number runs from a command."],
            foot_h="WHAT'S VERIFIED (reproducible from current main)",
            foot=[("3290", "tests collected · all green on CI"),
                  ("1.00", "QVT path_recall (median, paired)"),
                  ("0.58", "graded_answer baseline"),
                  ("0.67", "abstention F1"),
                  ("20 KB", "hard module-size cap on core/"),
                  ("4-rule", "LLM-free contradiction tree")],
        )
    # Korean
    return dict(
        font=FONT_KO,
        tags="#그래프RAG    #재현가능RAG    #감사가능AI    #로컬우선",
        title="PROJECT JAMES",
        subtitle="로컬 우선·감사 가능한 지식 추론 플랫폼 — 그래프-RAG 검색, 결정론적 "
                 "모순 중재, 그리고 바이트 단위로 동일한 재현 가능 상태.",
        badges=[("v0.4.1 · T6 인과 체인", "indigo"), ("MIT 라이선스", "green"),
                ("Python 3.11+", "blue"), ("테스트 3290개 · 전부 통과", "amber"),
                ("DOI 10.5281/zenodo.20426719", "purple"),
                ("모체 플랫폼 → v1.0", "red")],
        love_h="개발자가 자메스를 좋아하는 이유",
        love=[("로컬 우선", "완전 온프레미스 동작. 기본값에서 데이터가 밖으로 나가지 않음.", "green"),
              ("재현 가능 RAG", "reconstruct_view_at() 로 과거 상태를 바이트 단위로 복원.", "indigo"),
              ("추가 전용 감사로그", "모든 결정을 불변으로 기록 — 완전한 출처 추적.", "blue"),
              ("결정론적 중재기", "LLM 없는 4규칙 모순 트리, 재현 안전.", "amber"),
              ("플러그인 API", "타입 명세 모듈 경계. 코어 포크 없이 확장.", "purple"),
              ("기본 OFF 불변식", "새 라우팅 레이어는 OFF로 출시 — 켜기 전까지 동일.", "red")],
        vs_h="자메스 ≠ 평면 / 클라우드 RAG",
        vs=["재현 가능: 과거 상태를 근사가 아닌 정확히 복원.",
            "프롬프트 휴리스틱이 아닌 결정론적 모순 중재.",
            "신뢰 구역이 저신뢰 입력을 LLM 이전에 격리.",
            "온프레미스 소유권 + 정정 해자 — 벤더 종속 없음.",
            "클라우드 송출은 추상화 신뢰 계약으로 게이트."],
        arch_h="자메스 아키텍처 개요",
        entry_h="진입점",
        entry=[("프런트엔드 / API", "UI + REST 표면"),
               ("인증 + 정책엔진", "RBAC / ABAC · 단일 정책 출처"),
               ("쿼리 라우터", "의도 분류 · 범위 라우팅")],
        core_h="자메스 코어",
        core=[("하이브리드 검색", "벡터 + BM25 · 리랭크"),
              ("그래프 엔진", "그래프-RAG · 타입 경로"),
              ("인지 미들웨어", "오토라우터 · 적응 예산 · 엔티티 앵커 · 쿼리 재작성"),
              ("추론 루프", "계획 → 검색 → 검증 → 합성"),
              ("신뢰 게이트 메모리", "에피소드 · 작업 · loom")],
        exec_h="실행 표면",
        exec=[("툴 라우터", "FS / 웹 샌드박스 · 허용목록"),
              ("클라우드 송출 구역", "추상화 모듈 · 마스킹 + 감사"),
              ("위키 생성기", "감사 가능한 지식 페이지"),
              ("출력 필터", "PII + 역할 마스킹")],
        state_h="상태 & 지식",
        state=[("Layer 4 라이프사이클", "T1 시간성 · T7 대체 · T2 모순 · T6 인과", "amber"),
               ("지식 캐스케이드 (L3)", "삭제 / 수정이 파생 사실로 전파", "red"),
               ("온톨로지 + 타입 필터", "관계 스키마 · 엔티티 타입 그래프 필터링", "indigo"),
               ("그래프 스냅샷 / 재현", "reconstruct_view_at — 'T시점에 무엇이 참?'", "green"),
               ("추가 전용 감사로그", "모든 상태 변경 불변 + 재현 가능", "blue")],
        how_h="자메스 동작 방식",
        how=[("1", "라우팅", "쿼리 분류. 범위 + 예산 결정.", "blue"),
             ("2", "검색", "하이브리드 벡터+BM25 검색, 리랭크.", "indigo"),
             ("3", "탐색", "그래프 엔진이 타입 경로로 근거 수집.", "purple"),
             ("4", "추론", "루프가 계획·검증·합성 ↔ 메모리.", "amber"),
             ("5", "중재", "결정론적 4규칙 모순 트리.", "red"),
             ("6", "마스킹", "PII + 역할 기준 출력 필터.", "orange"),
             ("7", "감사", "추가 전용 로그가 모든 결정 기록.", "green")],
        cap_h="플랫폼 역량 (모체 플랫폼 → v1.0)",
        cap=["사설 코퍼스에 대한 감사 가능 그래프-RAG, 완전한 출처.",
             "시간여행 쿼리 — 임의 과거 시점의 지식 재구성.",
             "자기진화에 필수 인간 승인 게이트 (옵트인 전용).",
             "추상화 신뢰 계약 뒤의 하이브리드 클라우드 추론 계층.",
             "v0.5 후보: 기업 내부지식 온톨로지 (게이트 상태)."],
        spc_h="자메스가 특별한 이유",
        spc=["재현 가능 RAG — 구조적으로 바이트 단위 동일 과거 상태.",
             "결정론적 모순 중재 — 결정 경로에 LLM 없음.",
             "신뢰 구역이 모든 저신뢰 출처를 LLM 이전에 게이트.",
             "자기진화에 인간 승인 게이트 — 무단 자동배포 없음.",
             "재현 가능 + 인용 — 모든 핵심 수치를 명령으로 재생산."],
        foot_h="검증된 사실 (현재 main에서 재현 가능)",
        foot=[("3290", "테스트 수집 · CI 전부 통과"),
              ("1.00", "QVT path_recall (중앙값, 페어드)"),
              ("0.58", "graded_answer 베이스라인"),
              ("0.67", "abstention F1"),
              ("20 KB", "core/ 모듈 크기 상한"),
              ("4규칙", "LLM 없는 모순 트리")],
    )


# ---------------------------------------------------------------------------
# Assemble poster
# ---------------------------------------------------------------------------
def build(lang: str) -> str:
    c = content(lang)
    parts: list[str] = []
    y = PAD

    # --- header ---
    parts.append(tspan(PAD, y + 20, c["tags"], 18, "600", "#6D28D9"))
    y += 40
    parts.append(tspan(PAD, y + 52, c["title"], 66, "800", "#4338CA", spacing="-1.5"))
    y += 78
    sub_lines = wrap(c["subtitle"], INNER, 21)
    sub_svg, ny = lines_block(PAD, sub_lines, 21, "500", SUB, 1.34, y)
    parts.append(sub_svg)
    y = ny + 14
    badges = [_badge(t, k) for t, k in c["badges"]]
    bf = flow(badges, INNER, 10, uniform=False)
    parts.append(g(PAD, y, bf.svg))
    y += bf.h + SEC_GAP

    # --- row 1: love (2fr) + vs (1fr) ---
    love_w = (INNER - GAP) * 2 / 3
    vs_w = (INNER - GAP) / 3
    love_cards = [card((love_w - 2 * PANEL_PAD - 24) / 3, t, d, k) for t, d, k in c["love"]]
    mh = max(b.h for b in love_cards)
    love_cards = [Block(b.w, mh, _resize_bg(b.svg, b.w, mh)) for b in love_cards]
    love_flow = flow(love_cards, love_w - 2 * PANEL_PAD, 12)
    vs_block = bullets(vs_w - 2 * PANEL_PAD, c["vs"], "#6D28D9")
    rh = max(panel_total(love_flow), panel_total(vs_block))
    s1, _ = panel(PAD, y, love_w, c["love_h"], "green", love_flow, forced_total=rh)
    s2, _ = panel(PAD + love_w + GAP, y, vs_w, c["vs_h"], "purple", vs_block, forced_total=rh)
    parts.append(s1)
    parts.append(s2)
    y += rh + SEC_GAP

    # --- architecture band + 3 columns ---
    bsvg, bh = band(PAD, y, INNER, c["arch_h"])
    parts.append(bsvg)
    y += bh + 14
    col_w = (INNER - 2 * GAP) / 3
    cols = [("entry_h", "entry", "blue"), ("core_h", "core", "indigo"), ("exec_h", "exec", "green")]
    col_blocks = []
    for _, key, pal in cols:
        nodes = [node(col_w - 2 * PANEL_PAD, t, s, pal) for t, s in c[key]]
        col_blocks.append(_stack(nodes, col_w - 2 * PANEL_PAD, 10))
    cmax = max(b.h for b in col_blocks)
    arch_total = 0
    for i, (hk, key, pal) in enumerate(cols):
        cb = col_blocks[i]
        cb = Block(cb.w, cmax, cb.svg)  # pad to align bottoms (panel grows)
        s, ph = panel(PAD + i * (col_w + GAP), y, col_w, c[hk], pal, cb)
        parts.append(s)
        arch_total = max(arch_total, ph)
    y += arch_total + SEC_GAP

    # --- state & knowledge ---
    sk_cards = [card((INNER - 2 * PANEL_PAD - 4 * 12) / 5, t, d, k) for t, d, k in c["state"]]
    mh = max(b.h for b in sk_cards)
    sk_cards = [Block(b.w, mh, _resize_bg(b.svg, b.w, mh)) for b in sk_cards]
    sk_flow = flow(sk_cards, INNER - 2 * PANEL_PAD, 12)
    s, ph = panel(PAD, y, INNER, c["state_h"], "amber", sk_flow)
    parts.append(s)
    y += ph + SEC_GAP

    # --- how it works band + steps ---
    bsvg, bh = band(PAD, y, INNER, c["how_h"])
    parts.append(bsvg)
    y += bh + 14
    step_w = (INNER - 6 * 12) / 7
    steps = [step_card(step_w, n, t, d, k) for n, t, d, k in c["how"]]
    mh = max(b.h for b in steps)
    steps = [Block(b.w, mh, _resize_bg(b.svg, b.w, mh)) for b in steps]
    sflow = flow(steps, INNER, 12)
    parts.append(g(PAD, y, sflow.svg))
    y += sflow.h + SEC_GAP

    # --- capabilities + special ---
    half = (INNER - GAP) / 2
    cap_b = bullets(half - 2 * PANEL_PAD, c["cap"], "#1D4ED8")
    spc_b = bullets(half - 2 * PANEL_PAD, c["spc"], "#6D28D9")
    rh = max(panel_total(cap_b), panel_total(spc_b))
    s1, _ = panel(PAD, y, half, c["cap_h"], "blue", cap_b, forced_total=rh)
    s2, _ = panel(PAD + half + GAP, y, half, c["spc_h"], "purple", spc_b, forced_total=rh)
    parts.append(s1)
    parts.append(s2)
    y += rh + SEC_GAP

    # --- footer numbers ---
    fn = [number_card((INNER - 2 * PANEL_PAD - 5 * 12) / 6, n, l, "#4338CA") for n, l in c["foot"]]
    mh = max(b.h for b in fn)
    fn = [Block(b.w, mh, _resize_bg(b.svg, b.w, mh)) for b in fn]
    fflow = flow(fn, INNER - 2 * PANEL_PAD, 12)
    s, ph = panel(PAD, y, INNER, c["foot_h"], "indigo", fflow,
                  header_bg="#0F172A", header_fg="#FFFFFF")
    parts.append(s)
    y += ph + PAD

    height = y
    body = "".join(parts)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height:.0f}" '
            f'viewBox="0 0 {W} {height:.0f}" font-family="{esc(c["font"])}">'
            f'{rect(0,0,W,height,BG,0)}{body}</svg>')


def _badge(text, key) -> Block:
    bg, fg = PAL[key]
    w = text_w(text, 13) + 28
    h = 34
    return Block(w, h, rect(0, 0, w, h, bg, 999) + tspan(14, 22, text, 13, "600", fg))


def _stack(blocks: list[Block], w: float, gap: float) -> Block:
    y = 0.0
    out = []
    for b in blocks:
        out.append(g(0, y, b.svg))
        y += b.h + gap
    return Block(w, max(0.0, y - gap), "".join(out))


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        import cairosvg  # optional: only needed for PNG/PDF rasterization
    except Exception:
        cairosvg = None
    for lang in ("en", "ko"):
        svg = build(lang)
        base = os.path.join(here, f"james_architecture_{lang}")
        with open(base + ".svg", "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(f"wrote {base}.svg ({len(svg)} bytes)")
        if cairosvg is not None:
            cairosvg.svg2png(url=base + ".svg", write_to=base + ".png", output_width=3280)
            cairosvg.svg2pdf(url=base + ".svg", write_to=base + ".pdf")
            print(f"wrote {base}.png + {base}.pdf")
        else:
            print("  (cairosvg not installed — skipped PNG/PDF; `pip install cairosvg`)")


if __name__ == "__main__":
    main()
