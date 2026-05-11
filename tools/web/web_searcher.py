"""
PROJECT JAMES — Web Searcher (3-E)

웹 검색 + 지식 연동 모듈.

검색 엔진 우선순위:
  1순위: Tavily  (AI 특화, 무료 1,000회/월, TAVILY_API_KEY 환경변수 필요)
  2순위: DuckDuckGo (무료, API 키 불필요, 자동 fallback)
  → Tavily 할당량 소진 또는 오류 시 DuckDuckGo로 자동 전환

단기/장기 지식 분리 원칙:
  [경로 A] 챗 대화 → 단기 시작
    retrieval score 낮음 → 자동 웹 검색
    → conversation_history에 단기 저장
    → 반복 2회+ 또는 "저장해줘" 명시 → 장기 전환 (wiki entity)

  [경로 B] 어드민 자기학습 → 바로 장기
    → wiki entity 직접 생성 + vector 인덱싱

보안:
  - admin 권한만 허용
  - 출처 URL audit 기록
"""

import os
import re
import time
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

# ── 상수 ────────────────────────────────────────────────────────
MAX_RESULTS   = 5       # 검색 결과 최대 개수
MAX_SNIPPET   = 400     # 스니펫 최대 글자 수
REPEAT_TH     = 2       # 단기→장기 자동 전환 반복 횟수
WEB_SEARCH_TH = 0.45    # 이 미만이면 웹 검색 실행 (RELEVANCE_GATE와 동일)

# Tavily 할당량 초과 여부 (세션 내 캐시)
_tavily_exhausted: bool = False

# 검색 반복 추적 (메모리 내, 서버 재시작 시 초기화)
_search_history: Dict[str, int] = {}   # topic_key → 검색 횟수


# ── Tavily 검색 ──────────────────────────────────────────────────

def _search_tavily(query: str, max_results: int) -> List[Dict]:
    """
    Tavily AI 검색 (1순위).
    환경변수 TAVILY_API_KEY 필요.
    [개선] advanced 모드 + raw_content로 본문 직접 받음.
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY 미설정")

    try:
        from tavily import TavilyClient
    except ImportError:
        raise RuntimeError("tavily 미설치 (pip install tavily-python)")

    client   = TavilyClient(api_key=api_key)
    response = client.search(
        query           = query,
        max_results     = max_results,
        search_depth    = "advanced",   # advanced → 본문 정제 품질↑
        include_raw_content = True,     # 사이트 본문 직접 반환
    )

    results = []
    for r in response.get("results", []):
        # raw_content 우선, 없으면 content
        body = r.get("raw_content", "") or r.get("content", "")
        snippet = r.get("content", "") or ""
        results.append({
            "title":   (r.get("title", "") or "")[:100],
            "url":     r.get("url", ""),
            "snippet": snippet[:MAX_SNIPPET],
            "body":    body[:3000] if body else "",   # Tavily가 이미 정제함
            "engine":  "tavily",
        })
    return results


# ── DuckDuckGo 검색 ──────────────────────────────────────────────

def _search_duckduckgo(query: str, max_results: int) -> List[Dict]:
    """
    DuckDuckGo 검색 (2순위 fallback, API 키 불필요).
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        raise RuntimeError("duckduckgo_search 미설치 (pip install duckduckgo-search)")

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title":   (r.get("title", "") or "")[:100],
                "url":     r.get("href", ""),
                "snippet": (r.get("body", "") or "")[:MAX_SNIPPET],
                "engine":  "duckduckgo",
            })
    return results


# ── 통합 검색 함수 ───────────────────────────────────────────────

def search_web(query: str, max_results: int = MAX_RESULTS) -> List[Dict]:
    """
    웹 검색 — Tavily 우선, 실패 시 DuckDuckGo 자동 전환.

    반환: [{"title":..., "url":..., "snippet":..., "engine":...}, ...]
    """
    global _tavily_exhausted

    # ── 1순위: Tavily ──────────────────────────────────────────
    if not _tavily_exhausted and os.environ.get("TAVILY_API_KEY"):
        try:
            results = _search_tavily(query, max_results)
            if results:
                print(f"[WEB] Tavily 검색 성공: '{query[:30]}' ({len(results)}건)")
                return results
        except Exception as e:
            err_str = str(e).lower()
            # 할당량 초과 → 이후 DuckDuckGo로 고정
            if any(k in err_str for k in ["quota", "limit", "429", "rate", "exceeded"]):
                _tavily_exhausted = True
                print("[WEB] Tavily 할당량 초과 → DuckDuckGo fallback 전환")
            else:
                print(f"[WEB] Tavily 오류: {e} → DuckDuckGo fallback")

    # ── 2순위: DuckDuckGo ─────────────────────────────────────
    try:
        results = _search_duckduckgo(query, max_results)
        if results:
            engine_note = "(Tavily 소진됨)" if _tavily_exhausted else ""
            print(f"[WEB] DuckDuckGo 검색 성공: '{query[:30]}' ({len(results)}건) {engine_note}")
            return results
    except Exception as e:
        print(f"[WEB] DuckDuckGo 오류: {e}")

    # ── 실패 ──────────────────────────────────────────────────
    print("[WEB] 모든 검색 엔진 실패 — pip install tavily-python duckduckgo-search")
    return []


def get_search_engine_status() -> Dict:
    """현재 검색 엔진 상태 반환 (어드민 대시보드용)."""
    # ── TAVILY_API_KEY: os.environ 직접 읽기 (캐시 방지) ──
    has_tavily_key = bool(os.environ.get("TAVILY_API_KEY", "").strip())

    # ── Tavily 설치 감지: TavilyClient import로 확인 (최상위 패키지 대신) ──
    tavily_installed = False
    try:
        from tavily import TavilyClient  # 실제 사용하는 클래스로 감지  # noqa: F401
        tavily_installed = True
    except ImportError:
        try:
            import tavily  # fallback  # noqa: F401
            tavily_installed = True
        except ImportError:
            tavily_installed = False

    # ── DDG 설치 감지: DDGS 클래스로 확인 ──
    ddg_installed = False
    try:
        from duckduckgo_search import DDGS  # 실제 사용하는 클래스로 감지  # noqa: F401
        ddg_installed = True
    except ImportError:
        try:
            import duckduckgo_search  # noqa: F401
            ddg_installed = True
        except ImportError:
            ddg_installed = False

    if has_tavily_key and tavily_installed and not _tavily_exhausted:
        active = "tavily"
    elif ddg_installed:
        active = "duckduckgo"
    else:
        active = "none"

    print(f"[WEB_STATUS] key={has_tavily_key} pkg={tavily_installed} ddg={ddg_installed} → {active}")

    return {
        "active_engine":    active,
        "tavily_key":       has_tavily_key,
        "tavily_installed": tavily_installed,
        "tavily_exhausted": _tavily_exhausted,
        "ddg_installed":    ddg_installed,
    }


def format_search_results(results: List[Dict]) -> str:
    """LLM 프롬프트에 주입할 검색 결과 텍스트."""
    if not results:
        return ""
    lines = ["[🌐 웹 검색 결과]"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("body"):         # fetch된 본문 있으면 우선 사용
            lines.append(f"   [본문 발췌] {r['body'][:300]}")
        if r.get("url"):
            lines.append(f"   출처: {r['url']}")
    return "\n".join(lines)


def search_web_trusted(query: str, max_results: int = MAX_RESULTS):
    """[#44 phase 4-C] 검색 결과를 `TrustedContent(source="web", trust="low")` 로 wrap.

    `search_web` + `format_search_results` 의 thin wrapper. 호출자는
    구조화된 dict 가 필요하면 `search_web` 를 직접 호출하고, LLM 컨텍스트로
    합류시킬 텍스트만 필요하면 이 함수를 사용해 producer-side 에서 trust
    boundary 를 명시적으로 표현한다 (`core.reasoning.pipeline` 의 web
    fallback 경로처럼 consumer-side 에서 wrap 하는 패턴의 대안).

    프로듀서 측 wrapping 의 이점:
      - tool-router (현재 부재, future) 가 multimodal extractor 결과를
        `TrustedContent` 로 라우팅하기 시작하면 추가 변환 없이 호환.
      - 호출자가 `default_engine.quarantine(tc)` 한 줄로 처리 가능.

    Trust 분류 (#44 §3):
      - source = "web"   (외부 페이지 본문 / 검색 스니펫)
      - trust  = "low"   (제3자 저작, prompt-injection 위험)
    """
    from core.policy_engine import TrustedContent
    results = search_web(query, max_results)
    text    = format_search_results(results) if results else ""
    return TrustedContent(text=text, source="web", trust="low")


# ── URL 본문 fetch ────────────────────────────────────────────────

# 본문 fetch 스킵 도메인 (메타데이터만 나오는 곳)
SKIP_FETCH_DOMAINS = [
    "youtube.com", "youtu.be",        # 영상 — 자바스크립트 렌더링
    "instagram.com", "facebook.com",  # 로그인 필요
    "twitter.com", "x.com",           # 로그인 필요
    "tiktok.com",                     # 로그인 필요
    "linkedin.com",                   # 로그인 필요
    "reddit.com",                     # 자바스크립트 렌더링
]


def _is_quality_content(text: str) -> bool:
    """
    fetch한 텍스트가 의미있는 본문인지 검증.
    - 한국어/영어 글자 비율 ≥ 30%
    - 평균 단어 길이 ≥ 2
    - 너무 짧거나 메뉴 텍스트 잔재면 거부
    """
    if not text or len(text) < 200:
        return False

    # 한국어 + 영어 알파벳 비율
    alpha_kor = sum(1 for c in text if c.isalpha() or '가' <= c <= '힣')
    if alpha_kor / max(len(text), 1) < 0.3:
        return False

    # 단어 길이 (메뉴 잔재는 짧은 단어 많음)
    words = text.split()
    if len(words) < 30:
        return False
    avg_word_len = sum(len(w) for w in words) / len(words)
    if avg_word_len < 2.0:
        return False

    # UI 패턴 탐지 (로그인/구독/메뉴 등 반복)
    ui_patterns = ["로그인", "구독", "좋아요", "메뉴", "검색", "Login", "Subscribe"]
    ui_count = sum(text.count(p) for p in ui_patterns)
    if ui_count > len(words) * 0.1:  # UI 단어가 10% 넘으면 거부
        return False

    return True


def fetch_url_content(url: str, max_chars: int = 2000) -> str:
    """
    URL 본문을 가져와서 텍스트 추출.
    [개선] SKIP 도메인 + 품질 검증 → 의미있는 본문만 반환.
    """
    if not url:
        return ""

    # SKIP 도메인 체크
    url_lower = url.lower()
    for skip in SKIP_FETCH_DOMAINS:
        if skip in url_lower:
            print(f"[WEB_FETCH] SKIP {skip}: {url[:50]}... (snippet만 사용)")
            return ""

    try:
        import urllib.request
        import html
        import re as _re

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ko,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read(80000).decode("utf-8", errors="ignore")

        # HTML 태그 제거
        raw = _re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=_re.DOTALL)
        raw = _re.sub(r'<style[^>]*>.*?</style>',  '', raw, flags=_re.DOTALL)
        raw = _re.sub(r'<noscript[^>]*>.*?</noscript>', '', raw, flags=_re.DOTALL)
        raw = _re.sub(r'<nav[^>]*>.*?</nav>',     '', raw, flags=_re.DOTALL)
        raw = _re.sub(r'<header[^>]*>.*?</header>', '', raw, flags=_re.DOTALL)
        raw = _re.sub(r'<footer[^>]*>.*?</footer>', '', raw, flags=_re.DOTALL)
        raw = _re.sub(r'<[^>]+>', ' ', raw)
        raw = html.unescape(raw)
        raw = _re.sub(r'\s+', ' ', raw).strip()

        text = raw[:max_chars]

        # 품질 검증
        if not _is_quality_content(text):
            print(f"[WEB_FETCH] 품질 미달 (UI 잔재): {url[:50]}...")
            return ""

        return text

    except Exception as e:
        print(f"[WEB_FETCH] {url[:40]}... 실패: {e}")
        return ""


def enrich_results_with_content(
    results: List[Dict],
    max_fetch: int = 2,
) -> List[Dict]:
    """
    검색 결과 본문 보강.
    [개선]
      - Tavily 결과는 이미 raw_content 있으면 fetch 스킵
      - DDG 결과만 추가 fetch (상위 N개)
      - 품질 미달 시 snippet만 사용
    """
    enriched = []
    fetched  = 0
    for r in results:
        # Tavily가 이미 본문 제공한 경우
        if r.get("body") and r.get("engine") == "tavily":
            enriched.append(r)
            print(f"[WEB_FETCH] Tavily 본문 사용: {r['url'][:50]}... ({len(r['body'])}자)")
            fetched += 1
            continue

        # body 없는 결과 → 추가 fetch (상위 max_fetch개)
        if fetched < max_fetch and r.get("url"):
            body = fetch_url_content(r["url"])
            if body:
                r = {**r, "body": body}
                fetched += 1
                print(f"[WEB_FETCH] 본문 취득: {r['url'][:50]}... ({len(body)}자)")
            else:
                # fetch 실패 → snippet만 유지
                pass
        enriched.append(r)
    return enriched


# ── domain 분류 ───────────────────────────────────────────────────

_DOMAIN_MAP = {
    "security":  ["보안","해킹","취약","암호","인증","공격","방화벽","침해","security","cyber",
                  "sql","injection","xss","csrf","ddos","malware","exploit","penetration"],
    "coding":    ["파이썬","코드","알고리즘","개발","프로그램","api","라이브러리","python","code",
                  "framework","함수","클래스","디버그","컴파일","javascript","java","c++"],
    "business":  ["경제","비즈니스","시장","투자","전략","마케팅","매출","기업","스타트업",
                  "revenue","startup","finance","roi","kpi"],
    "science":   ["ai","머신러닝","딥러닝","과학","기술","연구","데이터","모델","neural",
                  "transformer","llm","gpt","bert","인공지능","machine learning"],
    "general":   [],   # fallback
}

def classify_domain(query: str, results: List[Dict] = None) -> str:
    """쿼리 + 검색 결과로 도메인 자동 분류."""
    text = query.lower()
    if results:
        text += " " + " ".join(r.get("snippet","")[:100] for r in results[:3]).lower()
    for domain, keywords in _DOMAIN_MAP.items():
        if any(kw in text for kw in keywords):
            return domain
    return "general"


# ── 개선된 save_as_longterm ──────────────────────────────────────

def save_as_longterm(
    query:     str,
    results:   List[Dict],
    summary:   str,
    user_role: str = "admin",
    domain:    str = "",        # [U-1] 도메인 명시 가능
) -> Optional[str]:
    """
    [U-1 개선] 웹 검색 결과 → wiki entity 생성 → vector 인덱싱.

    개선:
      ① URL 본문 fetch된 내용을 entity에 포함
      ② summary + body → 풍부한 wiki 본문 생성
      ③ domain 태그 자동 분류
      ④ entity['summary']에 LLM 요약 정확히 전달
    """
    if not results or not summary:
        return None

    # domain 자동 분류
    if not domain:
        domain = classify_domain(query, results)

    try:
        try:
            from core.graph_rag_engine import RAGEngine
        except ModuleNotFoundError:
            from graph_rag_engine import RAGEngine

        engine = RAGEngine(default_role=user_role)
        wg     = engine.wiki_generator
        topic  = _topic_key(query)
        sources= [r["url"]     for r in results if r.get("url")]
        bodies = [r.get("body","") or r.get("snippet","") for r in results]
        now    = datetime.now().isoformat()

        # [U-1] 본문 내용 조합 (LLM 요약 + 검색 본문 발췌)
        body_excerpt = "\n\n".join([
            b[:400] for b in bodies if b
        ][:3])

        # wiki 본문 내용 (## 섹션으로 구성)
        full_content = (
            f"{summary}\n\n"
            f"### 주요 내용\n{body_excerpt}\n\n"
            f"### 출처\n" + "\n".join(f"- {u}" for u in sources[:5])
        )

        entity = {
            "name":        topic,
            "entity_type": "concept",
            "sensitivity": "internal",
            "source_type": "prod",
            # [U-1] summary와 description 모두 채움
            "summary":     summary,          # wiki .md ## 요약 섹션에 사용
            "description": summary,          # frontmatter에 사용
            "attributes": {
                "domain":        domain,     # [U-1] 도메인 태그
                "web_sources":   sources,
                "learned_at":    now,
                "learn_method":  "web_search",
                "content_chars": len(body_excerpt),
            },
            "relations": [],
        }

        path = wg.create_entity_file(
            entity,
            filename  = f"web_{domain}_{topic[:20]}_{int(time.time())}.md",
            chunk_ids = [],
            user_role = user_role,
        )

        # [U-1] full_content로 vector 인덱싱 (summary만 아닌 전체 내용)
        try:
            from core.tokenizer import split_chunks
        except ImportError:
            def split_chunks(text, **kw):
                return [text[i:i+500] for i in range(0, len(text), 500)]

        chunks = split_chunks(full_content)
        engine.vector_store.add_documents_with_meta(
            texts    = chunks,
            source   = Path(path).name,
            metadata = {
                "sensitivity": "internal",
                "source_type": "prod",
                "owner":       "system",
                "domain":      domain,       # [U-1] 도메인 메타데이터
            },
        )

        wg.refresh_entity_map()
        print(f"[WEB→WIKI] 저장: {Path(path).name} | domain={domain} | {len(chunks)} chunks | {len(body_excerpt)}자")
        return path

    except Exception as e:
        print(f"[WEB→WIKI] 저장 실패: {e}")
        return None


# ── 단기/장기 연동 ────────────────────────────────────────────────

def _topic_key(query: str) -> str:
    """검색 반복 추적을 위한 topic 키 생성."""
    # 조사/어미 제거 후 핵심 단어 추출
    clean = re.sub(r'[은는이가을를이야에서의]|이란\?*|이뭐|알려줘|설명해|뭐야', '', query)
    return clean.strip()[:30]


def record_search(query: str) -> int:
    """검색 횟수 기록. 반환: 현재까지 검색 횟수."""
    key = _topic_key(query)
    _search_history[key] = _search_history.get(key, 0) + 1
    return _search_history[key]


def should_promote_to_longterm(query: str) -> bool:
    """단기→장기 자동 전환 조건 충족 여부."""
    key = _topic_key(query)
    return _search_history.get(key, 0) >= REPEAT_TH


def save_as_longterm(
    query: str,
    results: List[Dict],
    summary: str,
    user_role: str = "admin",
) -> Optional[str]:
    """
    [경로 A 장기 전환 / 경로 B 직접 저장]
    웹 검색 결과 → wiki entity 생성 → vector 인덱싱.
    반환: 생성된 wiki 파일 경로 (실패 시 None)
    """
    if not results or not summary:
        return None

    try:
        try:
            from core.graph_rag_engine import RAGEngine
        except ModuleNotFoundError:
            from graph_rag_engine import RAGEngine

        engine   = RAGEngine(default_role=user_role)
        wg       = engine.wiki_generator

        # entity 정보 구성
        topic    = _topic_key(query)
        sources  = [r["url"] for r in results if r.get("url")]
        "\n".join(f"- {u}" for u in sources[:3])
        now      = datetime.now().isoformat()

        entity = {
            "name":        topic,
            "entity_type": "concept",
            "sensitivity": "internal",
            "source_type": "prod",
            "description": summary,
            "attributes": {
                "web_sources":   sources,
                "learned_at":    now,
                "learn_method":  "web_search",
            },
            "relations": [],
        }

        # wiki .md 파일 생성
        path = wg.create_entity_file(
            entity,
            filename=f"web_{topic[:20]}_{int(time.time())}.md",
            chunk_ids=[],
            user_role=user_role,
        )

        # vector 인덱싱
        content = Path(path).read_text(encoding="utf-8")
        try:
            from core.tokenizer import split_chunks
        except ImportError:
            def split_chunks(text, **kw):
                return [text[i:i+500] for i in range(0, len(text), 500)]

        chunks = split_chunks(content)
        engine.vector_store.add_documents_with_meta(
            texts=chunks,
            source=Path(path).name,
            metadata={"sensitivity": "internal", "source_type": "prod", "owner": "system"},
        )

        # entity_id_index 갱신
        wg.refresh_entity_map()

        print(f"[WEB→WIKI] 장기 저장 완료: {Path(path).name} ({len(chunks)} chunks)")
        return path

    except Exception as e:
        print(f"[WEB→WIKI] 장기 저장 실패: {e}")
        return None


# ── KnowledgeTracker 연동 ─────────────────────────────────────────

def update_knowledge_level(query: str, is_longterm: bool = False):
    """
    웹 검색 지식 획득 → KnowledgeTracker 도메인 레벨 업.
    단기: +2점 / 장기: +5점
    """
    try:
        from core.knowledge_tracker import KnowledgeTracker
        kt = KnowledgeTracker()
        domain = kt.classify_domain(query) if hasattr(kt, 'classify_domain') else "general"
        delta  = 5.0 if is_longterm else 2.0

        from core.knowledge_tracker import classify_domain
        domain = classify_domain(query)

        kt._scores[domain] = kt._scores.get(domain, 0.0) + delta
        kt._save()
        print(f"[KNOWLEDGE] {domain} +{delta}점 ({'장기' if is_longterm else '단기'} 웹 학습)")
    except Exception as e:
        print(f"[KNOWLEDGE] 레벨 업데이트 실패: {e}")


# ── 장기 저장 트리거 명령 감지 ────────────────────────────────────

SAVE_TRIGGERS = [
    r"(이거|이것|이 내용|방금|이 정보).{0,10}(저장|기억|위키|정리|추가)",
    r"(나중에|앞으로).{0,10}(쓸|쓰게|사용|참고)",
    r"(알아두|기억해|저장해)(줘|라|요)",
]

def is_save_command(query: str) -> bool:
    """사용자가 명시적으로 저장을 요청했는지."""
    for pattern in SAVE_TRIGGERS:
        if re.search(pattern, query):
            return True
    return False
