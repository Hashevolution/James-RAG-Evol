"""
PROJECT JAMES - 토크나이저 유틸리티
"""
import re

def tokenize(text):
    """
    한국어+영어 토크나이저
    - 조사/어미 제거 확장
    - 불용어 필터링 추가
    - 빈 토큰 제거
    """
    words = re.findall(r'[가-힣a-zA-Z0-9]+', text.lower())
    # 확장 조사/어미 목록
    josa_pattern = (
        r'(이었다|이다|입니다|했다|합니다|했습니다|있다|없다|된다|된다|'
        r'에서|으로|로서|로써|에게|한테|에게서|한테서|'
        r'에서는|에서도|에서만|에서부터|'
        r'이라고|라고|이라는|라는|이란|란|'
        r'이지만|지만|이나|나|이며|며|이고|고|'
        r'은|는|이|가|을|를|의|에|로|으로|와|과|도|만|까지|부터|'
        r'이라|라|으로서|로서)$'
    )
    # 불용어 목록
    stopwords = {
        "있", "없", "하", "되", "이", "그", "저", "것", "수", "등",
        "및", "또", "또는", "혹은", "그리고", "하지만", "그러나",
        "the", "a", "an", "is", "are", "was", "were", "of", "in",
        "to", "for", "and", "or", "but", "with", "at", "by"
    }
    cleaned = []
    for w in words:
        w = re.sub(josa_pattern, '', w)
        if w and len(w) >= 1 and w not in stopwords:
            cleaned.append(w)
    return cleaned

def split_chunks(text: str, chunk_size: int = 500, overlap: int = 50) -> list:
    """
    Heading → 문단 → 문장 → 고정크기 순서로 분할
    overlap 적용, rag_engine.py와 동일 로직

    γ cycle reverted (2026-06-03): chunk_size 2048 실측 결과 — step7
    regression + multihop no help + latency +1.4s. 500 chars 원복.
    학계 기지 hypothesis ("bigger chunks help multi-hop") 가 JAMES
    corpus + 현 pipeline 에서 작동 안 함 confirmation. 자세한 내용은
    `memory/feedback_gamma_chunk_size_no_improvement.md` 참조.
    """
    import re as _re
    if not isinstance(text, str) or not text.strip():
        return []

    chunks = []

    # 1단계: heading 기준 분할
    heading_pat = _re.compile(r'(?=^#{1,3} )', _re.MULTILINE)
    sections = heading_pat.split(text)
    if len(sections) <= 1:
        sections = _re.split(r'\n{2,}', text)

    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= chunk_size:
            chunks.append(section)
        else:
            # 문장 단위 분할
            sentences = _re.split(r'(?<=[.!?。\n]) ', section)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) <= chunk_size:
                    current += (" " if current else "") + sent
                else:
                    if current:
                        chunks.append(current.strip())
                    current = sent
            if current:
                chunks.append(current.strip())

    # 2단계: overlap 적용
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i-1][-overlap:] if len(chunks[i-1]) > overlap else chunks[i-1]
            overlapped.append(prev_tail + " " + chunks[i])
        chunks = overlapped

    # 3단계: 과도하게 긴 chunk 재분할
    final = []
    for c_item in chunks:
        c_item = c_item.strip()
        if not c_item:
            continue
        if len(c_item) > chunk_size * 2:
            for i in range(0, len(c_item), chunk_size - overlap):
                sub = c_item[i:i + chunk_size].strip()
                if sub:
                    final.append(sub)
        else:
            final.append(c_item)

    return final

def extract_names(question: str) -> list:
    """
    이름 후보 추출 (rag_engine.py에서 tokenizer로 통합)
    2~4글자 한국어 단어 중 불용어 제외
    """
    words     = tokenize(question)
    stopwords = {"키는", "몸무게", "나이는", "무엇", "정보", "어디", "누구",
                 "공부", "연구", "분야", "직업", "소속", "기관", "무엇을"}
    return [w for w in words if 2 <= len(w) <= 4 and w not in stopwords]
