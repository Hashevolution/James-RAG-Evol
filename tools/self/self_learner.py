"""
PROJECT JAMES — Self Learner (Phase 8, P8-LEARN-1)

자메스가 스스로 새로운 지식을 학습하고 wiki를 갱신.

현재 (P8-LEARN-1):
  LLM 내장 지식 + 기존 Wiki 융합 → 새 지식 생성
  반복 오류 쿼리 → LLM이 해당 주제 지식 생성 → wiki 저장

미래 (P8-WEB-1 이후):
  웹 검색 결과 + LLM + Wiki 3자 융합
  [WEB_SEARCH_PLACEHOLDER] 부분이 자동 활성화됨

학습 흐름:
  ImportanceScorer → 반복 오류 쿼리 감지
       ↓
  SelfLearner.learn() → LLM으로 지식 생성
       ↓
  품질 검증 (LLM 자기 검토)
       ↓
  EvoAnalyzer → wiki_add 제안 생성
       ↓
  Admin 승인 → wiki 저장 + 재인덱싱
"""

import re
from datetime import datetime
from typing import Optional, Dict, List

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."


class SelfLearner:
    """
    자기학습 엔진.
    LLM 지식 + 기존 Wiki로 새 지식을 생성해서 제안.
    """

    def __init__(self, llm=None):
        self._llm = llm

    def _get_llm(self):
        if self._llm is None:
            try:
                from llm.router import RouterWrapper
                self._llm = RouterWrapper("general")
            except Exception:
                pass
        return self._llm

    # ─── 핵심: 지식 생성 ────────────────────────────────────────

    def learn(self, topic: str, context: str = "",
              web_search: bool = False) -> Optional[Dict]:
        """
        주제에 대한 새 지식 생성.

        Args:
            topic:      학습할 주제
            context:    기존 Wiki 컨텍스트 (있으면 활용)
            web_search: 웹 검색 활용 여부 (P8-WEB-1 이후 활성화)

        Returns:
            {
              "topic":     str,
              "content":   str (wiki md 형식),
              "quality":   0.0~1.0,
              "sources":   ["LLM", "Wiki", "Web"(예정)],
              "proposal":  proposal dict
            }
        """
        llm = self._get_llm()
        if llm is None:
            return None

        sources  = ["LLM"]
        web_info = ""

        # [WEB_SEARCH_PLACEHOLDER]
        # P8-WEB-1 완성 후 아래 주석 해제
        # if web_search:
        #     from tools.web.searcher import search
        #     web_results = search(topic, limit=3)
        #     web_info = "\n".join([r["snippet"] for r in web_results])
        #     sources.append("Web")

        # 기존 Wiki 컨텍스트 활용
        if context:
            sources.append("Wiki")

        # 1단계: 지식 생성
        gen_prompt = self._build_gen_prompt(topic, context, web_info)
        content = llm.call_gemma(gen_prompt, timeout=90, use_cache=False)

        if not content or len(content) < 100:
            print(f"[LEARN] '{topic}' 지식 생성 실패")
            return None

        # 2단계: 자기 검토 (품질 평가)
        quality = self._self_review(topic, content, llm)

        if quality < 0.4:
            print(f"[LEARN] '{topic}' 품질 미달 ({quality:.2f}) — 제안 보류")
            return None

        # 3단계: wiki md 포맷으로 변환
        wiki_content = self._to_wiki_format(topic, content, sources)

        # 4단계: EvoAnalyzer 제안 생성
        proposal = self._make_learn_proposal(topic, wiki_content, quality, sources)

        print(f"[LEARN] '{topic}' 학습 완료 "
              f"(quality={quality:.2f}, sources={sources})")

        return {
            "topic":    topic,
            "content":  wiki_content,
            "quality":  quality,
            "sources":  sources,
            "proposal": proposal,
        }

    def learn_from_errors(self, min_count: int = 2) -> List[Dict]:
        """
        반복 오류 쿼리 자동 학습.
        ImportanceScorer에서 오류 패턴 가져와서 일괄 학습.
        """
        from tools.self.importance_scorer import get_repeated_errors

        errors   = get_repeated_errors(min_count)
        results  = []
        llm      = self._get_llm()
        if not llm or not errors:
            return []

        for error in errors[:3]:   # 최대 3개씩
            topic = error["query"]
            print(f"[LEARN] 오류 쿼리 학습: '{topic[:40]}' ({error['count']}회)")

            # 기존 wiki 컨텍스트 조회
            context = self._fetch_wiki_context(topic)
            result  = self.learn(topic, context)
            if result:
                results.append(result)

        return results

    def continuous_improve(self, topics: List[str]) -> List[Dict]:
        """
        주제 목록에 대한 연속 학습.
        관리자가 직접 학습 주제를 지정할 때 사용.
        """
        results = []
        for topic in topics[:5]:   # 최대 5개
            context = self._fetch_wiki_context(topic)
            result  = self.learn(topic, context)
            if result:
                results.append(result)
        return results

    # ─── 헬퍼 ─────────────────────────────────────────────────

    def _build_gen_prompt(self, topic: str, context: str, web_info: str) -> str:
        ctx_block = f"\n[기존 자료]\n{context[:600]}\n" if context else ""
        web_block = f"\n[웹 정보]\n{web_info[:600]}\n" if web_info else ""

        return (
            f"다음 주제에 대한 정확하고 유용한 지식을 작성해줘.\n"
            f"주제: {topic}\n"
            f"{ctx_block}{web_block}\n"
            f"형식 (마크다운):\n"
            f"# {{주제}}\n\n"
            f"{{핵심 개념 설명 2~3문장}}\n\n"
            f"## 주요 특징\n- {{특징1}}\n- {{특징2}}\n- {{특징3}}\n\n"
            f"## 관련 개념\n- {{관련1}}\n- {{관련2}}\n\n"
            f"지식 작성:"
        )

    def _self_review(self, topic: str, content: str, llm) -> float:
        """LLM이 자신이 생성한 지식의 품질을 자기 평가 (0~1)."""
        review_prompt = (
            f"다음 지식의 품질을 평가해줘. 0.0~1.0 숫자만 답변.\n"
            f"주제: {topic}\n내용:\n{content[:500]}\n\n"
            f"평가 기준: 정확성, 유용성, 완성도\n"
            f"점수 (숫자만):"
        )
        try:
            raw = llm.call_gemma(review_prompt, timeout=30, use_cache=False)
            nums = re.findall(r'0\.\d+|1\.0|[01]', raw or "")
            if nums:
                return min(max(float(nums[0]), 0.0), 1.0)
        except Exception:
            pass
        return 0.6   # 평가 실패 시 기본값

    def _to_wiki_format(self, topic: str, content: str, sources: List[str]) -> str:
        """wiki md 포맷으로 변환."""
        now = datetime.now().isoformat()
        normalized = re.sub(r'[^\w가-힣]', '_', topic).strip('_')

        header = (
            f"---\n"
            f"entity_id: learn_{normalized}_{now[:10].replace('-','')}\n"
            f"name: {topic}\n"
            f"entity_type: concept\n"
            f"sensitivity: internal\n"
            f"source_type: prod\n"
            f"created_at: {now}\n"
            f"generated_by: self_learner\n"
            f"sources: {', '.join(sources)}\n"
            f"relations: []\n"
            f"---\n\n"
        )

        # 헤더 중복 방지
        if content.strip().startswith("---"):
            return content
        if content.strip().startswith(f"# {topic}"):
            return header + content
        return header + f"# {topic}\n\n" + content

    def _make_learn_proposal(self, topic: str, content: str,
                              quality: float, sources: List[str]) -> Dict:
        """EvoAnalyzer 제안 생성."""
        try:
            from tools.self.evo_analyzer import _make_proposal, save_proposal
            normalized = re.sub(r'[^\w가-힣]', '_', topic).strip('_')
            p = _make_proposal(
                prop_type   = "wiki_add",
                title       = f"[자기학습] {topic}",
                description = (
                    f"자기학습으로 생성된 지식 — 품질 {quality:.0%}\n"
                    f"출처: {', '.join(sources)}\n"
                    f"admin 검토 후 적용 권장"
                ),
                content     = content,
                metadata    = {
                    "entity_name":  topic,
                    "entity_type":  "concept",
                    "source_query": topic,
                    "quality":      quality,
                    "sources":      sources,
                    "self_learned": True,
                }
            )
            save_proposal(p)
            return p
        except Exception as e:
            print(f"[LEARN] 제안 생성 실패: {e}")
            return {}

    def _fetch_wiki_context(self, topic: str) -> str:
        """기존 wiki에서 관련 컨텍스트 조회."""
        try:
            try:
                from core.graph_rag_engine import RAGEngine
            except ModuleNotFoundError:
                from graph_rag_engine import RAGEngine
            engine  = RAGEngine(default_role="admin")
            results = engine.vector_store.search(topic, top_k=3)
            if results:
                return "\n".join([r.get("text", "") for r in results[:3]])
        except Exception:
            pass
        return ""


# ─── 싱글턴 ─────────────────────────────────────────────────────

_learner: Optional[SelfLearner] = None

def get_learner() -> SelfLearner:
    global _learner
    if _learner is None:
        _learner = SelfLearner()
    return _learner

def learn_topic(topic: str, context: str = "") -> Optional[Dict]:
    """단일 주제 학습."""
    return get_learner().learn(topic, context)

def learn_from_errors() -> List[Dict]:
    """반복 오류 쿼리 자동 학습."""
    return get_learner().learn_from_errors()

def continuous_learn(topics: List[str]) -> List[Dict]:
    """연속 학습."""
    return get_learner().continuous_improve(topics)
