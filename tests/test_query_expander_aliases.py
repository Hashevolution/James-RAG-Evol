"""
PROJECT JAMES — Query Expander cross-lingual alias contract tests.

RAG corpus가 영문 PDF + 한국어 entity 혼재일 때 한↔영 alias가 query
expansion에 포함되는지 contract pin. 자세한 원인은
`memory/feedback_rag_cross_lingual_diagnostic.md` 참조.
"""

from core.query_expander import expand


def test_korean_company_expands_to_english_alias():
    # 팔란티어 query는 영문 chunk와 매칭돼야 함 (Palantir / PLTR)
    expanded = expand("팔란티어가 뭐야")
    assert "Palantir" in expanded
    assert "PLTR" in expanded


def test_english_company_expands_to_korean_alias():
    # 역방향: 영문 query도 한국어 chunk 매칭
    expanded = expand("What is Palantir doing")
    assert "팔란티어" in expanded


def test_nvidia_korean_to_english():
    expanded = expand("엔비디아 실적")
    assert "Nvidia" in expanded or "NVIDIA" in expanded
    assert "NVDA" in expanded


def test_alias_passthrough_when_no_match():
    # 매핑 없는 entity는 원본 그대로
    out = expand("xkzq존재하지않는단어")
    assert out == "xkzq존재하지않는단어"


def test_empty_query_passthrough():
    assert expand("") == ""
    assert expand("   ") == "   "


def test_alias_does_not_break_existing_synonyms():
    # 기존 일반 동의어 (AI → 인공지능) regression 안 깨짐
    expanded = expand("AI 연구")
    assert "인공지능" in expanded


def test_token_hard_limit_respected_with_aliases():
    # alias 추가가 TOKEN_HARD_LIMIT=50 안에서 동작
    from core.query_expander import TOKEN_HARD_LIMIT, _tokenize_simple
    expanded = expand("팔란티어 엔비디아 테슬라 애플 구글 메타 아마존")
    assert len(_tokenize_simple(expanded)) <= TOKEN_HARD_LIMIT
