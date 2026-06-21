"""Fast-path intent regex tables — split out of ``intent_classifier.py``.

Extracted (CLAUDE.md rule #5, 2026-06-21) so ``core/intent_classifier.py``
stays under the 20 KB cap. ``IntentClassifier.FAST_PATTERNS`` now
references this module-level dict (``FAST_PATTERNS = FAST_PATTERNS`` class
attribute), so ``self.FAST_PATTERNS`` and every pattern is byte-identical
to the pre-split version — only the home module changed.

Each entry maps a mode to a list of regexes that ``classify_fast``
matches WITHOUT an LLM call. Edits here are measurement-sensitive: the
v18.x comments document false-positive fixes caught by the pre-flight
intent sweep (English substrings in retrieval fixtures). Keep that
discipline when touching these patterns.
"""
from __future__ import annotations


# 즉시 분류 가능한 명확 패턴 (LLM 불필요)
FAST_PATTERNS = {
    "chat": [
        r"^(안녕|hi|hello|hey)\b",
        r"^(고마워|감사|ㅎㅎ|ㅋㅋ)\b",
        r"^.{1,3}$",                          # 3글자 이하
        r"^(remember|please remember|keep in mind|from now on)",
        r"^(i like|i prefer|i want|my name|my style)",
        # [STEP2-A FIX] 언어 변경 명령 → 반드시 chat (wiki_edit 오분류 방지)
        r"(영어|한국어|일본어|중국어|english|korean|japanese|chinese).{0,6}(로|으로|말해|해줘|답해|답변|바꿔|전환)",
        r"(다시|원래|이제).{0,6}(한국어|영어|korean|english)",
        r"^(영어로|한국어로|영어로만|한국어로만)\s*(말해|답해|해줘|해|줘)?$",
    ],
    "coding": [
        r"\b(python|파이썬|javascript|자바스크립트)\b",
        # v0.6.1 v18.3 (2026-06-16) — measurement-validity fix.
        # The old form "\b(def |class |import |traceback)\b"
        # matched English "class " in retrieval queries
        # (class-action lawsuit / first-class / world-class).
        # pre-flight retroactive sweep caught this — 7/75
        # MultiHop-RAG answerable queries falsely classified.
        # Predates the v0.6.1 cycle (initial release), but the
        # measurement guard exposes long-running bugs too.
        # Fix: require code-context follow-up — the next char
        # after the keyword is `(` / `[` / identifier-friendly,
        # which English prose doesn't produce after `class `.
        r"\b(def|class)\s+[A-Za-z_][\w]*\s*[\(:\[]",
        r"(?:^|\n)\s*(?:from\s+[A-Za-z_][\w.]*\s+)?import\s+[A-Za-z_][\w]*(?:\s*,\s*[A-Za-z_][\w]*)*\s*(?:as\s+[A-Za-z_][\w]*)?\s*(?:#|$|\n)",
        r"\bTraceback\s+\(most recent call last\)",
        r"(코드 작성|코드 수정|버그 찾아|코드 만들어|스크립트)",
    ],
    "self_evolve": [
        r"(네|너|자메스).{0,10}(코드|파일|구조|기능).{0,10}(파악|분석|인식|확인)",
        r"(스스로|자신|자기).{0,10}(분석|개선|진화|파악)",
        r"(폴더|디렉토리).{0,10}(구조|확인|파악)",
        r"\w+\.py.{0,20}(분석|확인|읽어|봐|줘)",
    ],
    "wiki_edit": [
        r"(수정|변경|고쳐|바꿔)(해|봐|줘|라)",
        r"(삭제|지워|제거)(해|봐|줘|라)",
        r"(추가|더해|넣어)(해|봐|줘|라)",
        r"(로|으로)\s*(수정|변경|바꿔|고쳐)",
        r"(잘못|틀렸|틀렸어|잘못됐)",
    ],
    # Meta / inventory queries — "what do you have?", "list everything",
    # "wiki 목록", "내부 자료 보여줘". These previously fell through to
    # `retrieval` and produced hallucinated answers because the wiki
    # file *list* is not in any vector chunk. Now routed to handle_meta
    # which calls tools/wiki/wiki_editor.py::list_entities() directly.
    #
    # Patterns must combine an inventory verb (목록 / 보여 / 알려 / 뭐
    # / 있는지 / list / show / what ... do you have) with a wiki/data
    # noun (wiki / 자료 / 문서 / 데이터 / entity / knowledge). This
    # keeps "BlackRock 목록 알려줘" (specific topic) out of meta.
    "meta": [
        # 캐논 형식: "wiki 목록", "내부 자료 보여줘"
        r"(wiki|위키|내부\s*자료|보유\s*자료|가지고\s*있는)\s*(목록|리스트|보여)",
        r"(어떤|무슨)\s*(자료|문서|wiki|위키|entity|엔티티).{0,15}(있|가지)",
        # v0.6.1 v17 (2026-06-16) — "무엇" 토큰도 받아들임. 운영자가
        # 자연어로 "내부 자료가 무엇이 있나" 처럼 자주 사용.
        r"(자료|데이터|문서|wiki|entity|knowledge|것).{0,8}(무엇|뭐가|뭐|어떤|무슨).{0,5}(있|가지)",
        r"(어떤|무슨|무엇|뭐가).{0,5}(자료|문서|데이터|wiki|위키|entity|엔티티).{0,15}(있|가지|보유)",
        r"^(자료|문서|entity|엔티티)\s*(목록|리스트)\s*[?\.!]?$",
        # 캐주얼 한국어: "데이터 뭐 있는지", "문서 뭐가 있어"
        r"(데이터|자료|문서|wiki|위키|entity|엔티티|knowledge)\s*(뭐|무슨|어떤)",
        r"(뭐|무슨|어떤)\s*(자료|문서|데이터|wiki|entity)\s*(있|가지|보유)",
        # 캐주얼 한국어: "저장된 데이터", "갖고 있는 자료", "보유 자료"
        r"(저장된|보유|갖고\s*있는|가지고\s*있는|아는)\s*\S{0,5}\s*(데이터|자료|문서|정보|내용|것|거)",
        # 캐주얼 한국어: "아는거 뭐 있어", "알고 있는 거 뭐"
        r"(아는|알고\s*있는)\s*(거|것).{0,8}(뭐|무슨|어떤)",
        r"내부\s*에?\s*(무슨|뭐|어떤)\s*(자료|문서|데이터|것|거)",
        # v0.6.1 v17 (2026-06-16) — meta inventory follow-up.
        # Operator catch: after the v16 hybrid overview, the natural
        # follow-up is "개념 자료에는 뭐가 있어?", "조직 리스트",
        # "AI 관련 자료", "최근 추가된 거" 류. These should land on
        # meta (not retrieval) so handle_meta can pivot the same
        # inventory by type / theme / recency. handle_meta inspects
        # the same query for filter keywords and renders the
        # appropriate detail view.
        # type 키워드 + (자료/항목/관련/것/들/리스트/목록 optional) +
        # (조사/공백 anywhere) + verb (누구·누가 포함)
        r"(개념|조직|기업|인물|보고서|문서|이벤트|장소|자산|미분류)\s*(자료|항목|관련|것|들|목록|리스트)?\s*\S{0,5}\s*(어떤|뭐|무슨|얼마|몇|있|보여|알려|누구|누가|목록|리스트)",
        # type 키워드 단독 + 명시 verb (리스트/목록) — "조직 리스트" 류.
        r"(개념|조직|기업|인물|보고서|문서|이벤트|장소|자산|미분류)\s*(목록|리스트)",
        # theme + 관련/쪽/는 + 자료/항목/리스트 OR 명시 verb. verb
        # 그룹은 optional — "AI 관련 자료" 같은 명사구만으로도 meta
        # 인텐트 인식 (v17 fix).
        r"(AI|에이아이|머신러닝|블록체인|크립토|crypto|web3|보안|security|연구|논문|연도별|연도|재무|시장|웹\s*자료)\s*(관련|쪽|쪽으로|에|는|을|의)\s*(자료|항목|것|들|목록|리스트|어떤|뭐|무슨|있|보여|알려)",
        r"(AI|에이아이|머신러닝|블록체인|크립토|crypto|web3|보안|security|연구|논문|연도별|연도|재무|시장|웹\s*자료)\s*(자료|항목|것|들|목록|리스트)\s*(어떤|뭐|무슨|있|보여|알려|\?)?",
        # v0.6.1 v18.1 (2026-06-16) — measurement-validity fix.
        # The v17 form had `recent|latest|new` with the trailing
        # noun group OPTIONAL, so bare English `new` / `News` /
        # `New York` substrings in retrieval queries (MultiHop-RAG
        # fixture) false-positive matched, polluting paired
        # measurements that pre-screen intent. Two-pattern split:
        # Korean tokens stay loose (no English false positives
        # because Korean characters never appear inside English
        # words), English tokens REQUIRE an explicit inventory
        # noun follow-up.
        # v0.6.1 v18.7 (2026-06-20) — fix: marker without an
        # explicit inventory noun was over-matching retrieval
        # queries ("OpenAI의 최신 모델 전략", "최신 소식 알려줘").
        # The trailing inventory-noun group was OPTIONAL in v17;
        # required now so the pattern only matches when both a
        # recency marker AND an inventory noun appear together.
        r"(최근|새로|새로운|새로\s*추가|최신|방금|어제|오늘)\s*(추가|들어온|올라온|업로드)?\s*\S{0,6}\s*(자료|항목|것|것들|문서|entity)",
        r"\b(recent|latest|new)\s+(additions|entries|files|documents|entities|items|uploads|content)\b",
        # v0.6.1 v18 (2026-06-16) — narrative trigger: "요약/정리/
        # 전체적으로/총평". Routes to handle_meta which then
        # detects the narrative keyword and runs the LLM
        # variant. Distinct from retrieval-summary because the
        # subject is the WHOLE corpus, not a specific topic.
        r"(보유\s*자료|내부\s*자료|자료|wiki|위키|entity)\s*(전체|모두|싹|싹\s*다)?\s*(요약|정리|총평|보고)",
        r"(전체적|총괄|총평).{0,6}(자료|wiki|위키|보고|정리|요약)",
        r"(요약|정리)해\s*줘\s*$",
        # 영어 — 더 유연하게 (PR #73 패턴은 'what do you' 만 잡음)
        r"(list|show)\s+(all\s+|me\s+)?(your\s+)?(entities|wiki|documents|files|data|knowledge)",
        r"^what\s+(\S+\s+){0,3}do\s+you\s+(have|know)",
        r"(your|the)\s+(knowledge\s*base|data\s*set|wiki|files|documents)\b",
    ],
}


__all__ = ["FAST_PATTERNS"]
