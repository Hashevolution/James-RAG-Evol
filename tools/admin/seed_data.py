"""
PROJECT JAMES — 시드 데이터 (테스트/검증용 기본 entity 8개)

구성:
  인물 3개   : 김민준(개발자), 이서연(분석가), 박지훈(보안전문가)
  조직 2개   : 자메스연구소, 보안기술팀
  개념 3개   : Graph-RAG, 자메스시스템, 보안추론

특징:
  - 양방향 관계 일관성 보장 (A→B면 B→A도 명시)
  - sensitivity 적절히 분배 (public/internal/confidential)
  - source_type=prod 로 통일 (test 폴더 폐기)
  - frontmatter 표준 준수
"""

# Issue #2: cp949 콘솔에서 box-drawing 문자 크래시 방지.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__)))))
try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except ImportError:
    pass

from pathlib import Path
from datetime import datetime

try:
    from config import WIKI_DIR
except ImportError:
    import os as _os
    # 현재 파일 위치 기준 (tools/admin/) → 두 단계 위가 프로젝트 루트
    _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    WIKI_DIR = _os.path.join(_root, "wiki")


SEED_ENTITIES = [
    # ─── 인물 ─────────────────────────────────────────────────
    {
        "name": "김민준", "type": "person", "subdir": "person",
        "sensitivity": "internal",
        "relations": [
            {"target": "자메스연구소",  "type": "BELONGS_TO",  "confidence": 0.95},
            {"target": "Graph-RAG",     "type": "WORKS_ON",    "confidence": 0.90},
        ],
        "body": """## 개요
자메스연구소 소속 시니어 개발자. Graph-RAG 시스템의 핵심 구현 담당.

## 전문 분야
- Python 백엔드 개발 (FastAPI, SQLite)
- 벡터 데이터베이스 (ChromaDB)
- LLM 파인튜닝 및 프롬프트 엔지니어링

## 주요 활동
- Graph-RAG 엔진 설계 및 구현
- DFS 기반 추론 파이프라인 개발
- ABAC 보안 정책 통합

## 연락처
- 이메일: minjun.kim@james-lab.local
- 슬랙: @minjun
""",
    },
    {
        "name": "이서연", "type": "person", "subdir": "person",
        "sensitivity": "internal",
        "relations": [
            {"target": "자메스연구소",  "type": "BELONGS_TO",  "confidence": 0.95},
            {"target": "Graph-RAG",     "type": "WORKS_ON",    "confidence": 0.85},
        ],
        "body": """## 개요
자메스연구소 데이터 분석가. Graph-RAG의 검색 정확도 평가 및 성능 측정 담당.

## 전문 분야
- 정보 검색 시스템 평가 (precision, recall, NDCG)
- 통계 분석 및 A/B 테스트 설계
- 데이터 시각화

## 주요 활동
- HybridSearch 알고리즘 성능 분석
- 사용자 피드백 데이터 분석
- 도메인별 정확도 보고서 작성

## 협업
김민준과 함께 검색 엔진 튜닝 작업 수행 중.
""",
    },
    {
        "name": "박지훈", "type": "person", "subdir": "person",
        "sensitivity": "confidential",
        "relations": [
            {"target": "보안기술팀",     "type": "BELONGS_TO",  "confidence": 0.95},
            {"target": "보안추론",       "type": "WORKS_ON",    "confidence": 0.90},
        ],
        "body": """## 개요
보안기술팀 책임자. 자메스 시스템의 보안 정책 설계 및 침투 테스트 담당.

## 전문 분야
- ABAC/RBAC 권한 관리
- Prompt Injection 방어
- 데이터 유출 방지 (DLP)

## 주요 활동
- 보안 레이어 설계 (security_layer.py)
- Red Team 시나리오 작성 및 검증
- 민감 정보 마스킹 정책 수립

## 보안 등급
Confidential 권한 보유 — 모든 보안 정책 결정권 보유.
""",
    },

    # ─── 조직 (자메스 표준: 'org' 폴더, 'org' type) ─────────────
    {
        "name": "자메스연구소", "type": "org", "subdir": "org",
        "sensitivity": "public",
        "relations": [
            {"target": "김민준",         "type": "HAS_MEMBER",  "confidence": 0.95},
            {"target": "이서연",         "type": "HAS_MEMBER",  "confidence": 0.95},
            {"target": "자메스시스템",   "type": "DEVELOPS",    "confidence": 1.00},
        ],
        "body": """## 개요
PROJECT JAMES (자메스 시스템)을 개발하는 연구 조직.

## 미션
보안이 보장된 Graph-RAG 기반 지식 추론 엔진 개발.

## 핵심 가치
1. **보안 우선**: 모든 설계는 공격을 전제로 시작
2. **설명 가능성**: 모든 답변에 추론 경로 제공
3. **자가 진화**: 사용할수록 개선되는 시스템

## 구성원
- 김민준 (시니어 개발자)
- 이서연 (데이터 분석가)
- 보안기술팀 (별도 운영)

## 주요 프로젝트
- Graph-RAG 엔진
- 자메스 시스템 (PROJECT JAMES)
""",
    },
    {
        "name": "보안기술팀", "type": "org", "subdir": "org",
        "sensitivity": "internal",
        "relations": [
            {"target": "박지훈",         "type": "HAS_MEMBER",  "confidence": 0.95},
            {"target": "보안추론",       "type": "DEVELOPS",    "confidence": 0.95},
            {"target": "자메스시스템",   "type": "SECURES",     "confidence": 1.00},
        ],
        "body": """## 개요
자메스 시스템의 보안 전반을 책임지는 독립 조직.

## 책임 범위
- 보안 레이어 설계 및 운영
- 침투 테스트 및 취약점 진단
- 권한 관리 (ABAC/RBAC) 정책
- 사고 대응 및 감사 로그 분석

## 주요 산출물
- 보안 정책 문서
- Red Team 시나리오
- 보안 감사 보고서

## 책임자
박지훈 (Confidential 권한 보유)
""",
    },

    # ─── 개념 ─────────────────────────────────────────────────
    {
        "name": "Graph-RAG", "type": "concept", "subdir": "concept",
        "sensitivity": "public",
        "relations": [
            {"target": "자메스시스템",   "type": "PART_OF",     "confidence": 1.00},
            {"target": "김민준",         "type": "DEVELOPED_BY","confidence": 0.90},
            {"target": "이서연",         "type": "DEVELOPED_BY","confidence": 0.85},
        ],
        "body": """## 개요
Graph-Retrieval-Augmented Generation의 약어. 그래프 구조 기반 검색 증강 생성 기법.

## 핵심 구성
1. **Vector Search**: 의미 기반 유사도 검색
2. **Graph Traversal**: 엔티티 관계 그래프 탐색 (DFS)
3. **Hybrid Ranking**: 벡터 + BM25 + 키워드 통합 점수
4. **Context Fusion**: 검색 결과 + 그래프 경로 통합

## 단순 RAG 대비 장점
- 환각(hallucination) 감소
- 추론 경로 명시 (explainability)
- 다단계 추론 가능
- 관계 기반 정밀 검색

## 자메스 시스템에서의 구현
graph_rag_engine.py에 통합 구현됨. DFS 깊이 4, 점수 임계값 0.05 사용.
""",
    },
    {
        "name": "자메스시스템", "type": "concept", "subdir": "concept",
        "sensitivity": "public",
        "relations": [
            {"target": "Graph-RAG",      "type": "CONTAINS",    "confidence": 1.00},
            {"target": "보안추론",       "type": "CONTAINS",    "confidence": 1.00},
            {"target": "자메스연구소",   "type": "DEVELOPED_BY","confidence": 1.00},
            {"target": "보안기술팀",     "type": "SECURED_BY",  "confidence": 1.00},
        ],
        "body": """## 개요
PROJECT JAMES의 정식 명칭. 보안 중심 Graph-RAG 기반 지식 추론 시스템.

## 시스템 특징
- **로컬 우선**: Ollama/Gemma 기반 자체 호스팅
- **보안 통합**: ABAC + Prompt Injection 방어 + 출력 필터
- **자가 진화**: 사용 패턴 학습 및 자동 제안 생성
- **설명 가능**: 모든 답변에 그래프 경로 제공

## 기술 스택
- Python 3.11 (FastAPI)
- ChromaDB (벡터 저장소)
- Ollama (로컬 LLM 추론)
- SQLite (메모리/감사 로그)

## 개발 현황
Phase 7 완료. 자기진화 + 멀티모달 + 피드백 시스템 가동 중.

## 차별점 vs Hermes
Hermes가 빠른 배포와 범용 자동화를 목표로 한다면, 자메스는 보안과 추론 깊이를 최우선으로 한다.
""",
    },
    {
        "name": "보안추론", "type": "concept", "subdir": "concept",
        "sensitivity": "internal",
        "relations": [
            {"target": "자메스시스템",   "type": "PART_OF",     "confidence": 1.00},
            {"target": "박지훈",         "type": "WORKS_ON",    "confidence": 0.90},
            {"target": "보안기술팀",     "type": "DEVELOPED_BY","confidence": 1.00},
        ],
        "body": """## 개요
보안 정책을 추론 과정 자체에 통합한 자메스 시스템의 핵심 개념.

## 3단계 보안 통과
1. **Pre-check**: 입력 검증 + Prompt Injection 탐지
2. **In-process**: ABAC 기반 그래프/벡터 결과 필터링
3. **Post-check**: 출력 마스킹 (PII, 민감 키워드)

## 설계 원칙
- 보안은 기능이 아니라 전제
- 모든 단계는 공격을 가정
- "동작한다"보다 "유출되지 않는다"가 우선

## 구현 위치
- security_layer.py: 핵심 로직
- ABAC: 사용자 role + entity sensitivity 비교
- 출력 필터: 정규식 패턴 + role별 차단 키워드

## 책임자
박지훈 (보안기술팀 책임자)
""",
    },
]


# ──────────────────────────────────────────────────
# 파일 작성
# ──────────────────────────────────────────────────

def _generate_standard_entity_id(name: str, entity_type: str) -> str:
    """
    자메스 표준 entity_id 형식 생성.
    graph_engine.py의 INTEG 검증 정규식: ^e_[a-z]+_[a-f0-9]{8,10}$
    wiki_generator.py와 동일 알고리즘 (SHA256 + SALT)
    """
    import re as _re, hashlib as _hashlib
    normalized = _re.sub(r"[^\w가-힣]", "_", name.strip().lower())
    SALT = "JAMES_SECURE_V1"
    raw  = f"{normalized}_{entity_type}_{SALT}"
    h    = _hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"e_{entity_type}_{h}"


# 시드 entity 이름 → type 매핑 (target_id 자동 생성용)
_NAME_TYPE_MAP = {}


def _build_name_type_map(entities: list):
    """이름 → entity_type 매핑 미리 구축 (target_id 자동 생성용)."""
    global _NAME_TYPE_MAP
    _NAME_TYPE_MAP = {ent["name"]: ent["type"] for ent in entities}


def _resolve_target_id(target_name: str) -> str:
    """관계의 target 이름으로 entity_id 자동 생성."""
    target_type = _NAME_TYPE_MAP.get(target_name, "concept")
    return _generate_standard_entity_id(target_name, target_type)


def _frontmatter(entity: dict) -> str:
    """표준 frontmatter 생성 (자메스 graph_engine 호환 entity_id + target_id)."""
    now = datetime.now().isoformat()
    entity_id = _generate_standard_entity_id(entity["name"], entity["type"])

    rel_lines = ""
    if entity.get("relations"):
        rel_lines = "relations:\n"
        for r in entity["relations"]:
            target_id = _resolve_target_id(r["target"])
            rel_lines += (f"  - target: {r['target']}\n"
                          f"    target_id: {target_id}\n"   # ⚡ 자메스 표준 필수
                          f"    type: {r['type']}\n"
                          f"    confidence: {r['confidence']}\n")
    else:
        rel_lines = "relations: []\n"

    return (
        f"---\n"
        f"entity_id: {entity_id}\n"
        f"name: {entity['name']}\n"
        f"entity_type: {entity['type']}\n"
        f"sensitivity: {entity['sensitivity']}\n"
        f"source_type: prod\n"
        f"owner: system\n"
        f"created_at: {now}\n"
        f"generated_by: seed_data\n"
        f"{rel_lines}"
        f"---\n\n"
    )


def write_seed_files() -> int:
    """
    시드 entity를 wiki 폴더에 작성.
    자메스 표준 경로: wiki/entity/prod/{type}/{name}.md
    """
    _build_name_type_map(SEED_ENTITIES)

    wiki = Path(WIKI_DIR)
    count = 0

    for ent in SEED_ENTITIES:
        # ⚡ 자메스 표준: wiki/entity/{source_type}/{type}/
        target_dir = wiki / "entity" / "prod" / ent["subdir"]
        target_dir.mkdir(parents=True, exist_ok=True)

        path = target_dir / f"{ent['name']}.md"
        content = _frontmatter(ent) + f"# {ent['name']}\n\n" + ent["body"]
        path.write_text(content, encoding="utf-8")
        print(f"      ✓ {ent['type']:8s} {ent['name']:15s} → entity/prod/{ent['subdir']}/{ent['name']}.md")
        count += 1

    return count


if __name__ == "__main__":
    n = write_seed_files()
    print(f"\n시드 {n}개 entity 작성 완료")
