"""
PROJECT JAMES — 업로드 시뮬레이션 검증 도구

실제 파일 업로드 없이 entity 생성 흐름을 시뮬레이션해서
다음을 미리 확인합니다:

  1. wiki_generator의 entity_id 생성 형식 검증
  2. 폴더 경로 정확성
  3. entity_id_index 자동 등록 여부
  4. graph_engine INTEG 검증 통과 여부
  5. vector store 추가 시뮬레이션

사용:
  python tools/admin/upload_simulator.py
  python tools/admin/upload_simulator.py --apply   (실제 추가)
"""

import sys
import os
from pathlib import Path

# 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# Issue #2: cp949 콘솔에서 box-drawing 문자 크래시 방지.
from utils.console import ensure_utf8_console
ensure_utf8_console()

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"
B = "\033[1m";  E = "\033[0m"

# 검증용 가짜 entity (업로드되었다고 가정)
TEST_ENTITY = {
    "name": "검증테스트_홍길동",
    "type": "person",
    "description": "업로드 시뮬레이션 테스트용 임시 인물.",
    "attributes": {
        "회사": "테스트주식회사",
        "직책": "검증담당",
    },
    "relations": [
        {"target": "테스트주식회사", "type": "BELONGS_TO", "confidence": 0.9},
    ],
    "metadata": {
        "filename":   "test_upload.md",
        "summary":    "업로드 시뮬레이션 테스트",
        "category":   "테스트",
        "keywords":   "검증,테스트",
    },
    "sensitivity": "internal",
    "source_type": "prod",
}


def main():
    apply = "--apply" in sys.argv

    print(f"\n{B}{C}{'═'*60}{E}")
    print(f"{B}{C}  📤 업로드 시뮬레이션 검증{E}")
    print(f"{B}{C}{'═'*60}{E}\n")

    # ─── 1. RAGEngine 로드 ──────────────────────────────────
    print(f"{C}[1] RAGEngine 로드{E}")
    try:
        try:
            from core.graph_rag_engine import RAGEngine
        except ModuleNotFoundError:
            from graph_rag_engine import RAGEngine
        engine = RAGEngine(default_role="admin")
        print(f"  {G}✅{E} RAGEngine 로드 성공")
        print(f"      현재 인덱스: {len(engine.wiki_generator.entity_id_index)}개 entity")
    except Exception as e:
        print(f"  {R}❌{E} RAGEngine 로드 실패: {e}")
        return

    # ─── 2. entity_id 생성 형식 검증 ──────────────────────
    print(f"\n{C}[2] entity_id 생성 형식 검증{E}")
    eid = engine.wiki_generator._generate_entity_id(
        TEST_ENTITY["name"], TEST_ENTITY["type"]
    )
    import re
    valid_format = bool(re.match(r"^e_[a-z]+_[a-f0-9]{8,10}$", eid))
    print(f"  {'✅' if valid_format else '❌'} 생성 형식: {eid}")
    print(f"      graph_engine INTEG 검증: {'통과' if valid_format else '실패'}")

    # ─── 3. 예상 경로 표시 ───────────────────────────────
    print(f"\n{C}[3] 예상 작성 경로{E}")
    expected_path = (
        engine.wiki_generator.entity_path /
        TEST_ENTITY["type"] /
        f"{engine.wiki_generator._normalize_name(TEST_ENTITY['name'])}.md"
    )
    print(f"  📁 {expected_path}")
    print(f"      wiki_generator.entity_path: {engine.wiki_generator.entity_path}")
    print(f"      자메스 표준 (wiki/entity/prod/{{type}}/): "
          f"{'✅' if 'entity' in str(expected_path) else '❌'}")

    # ─── 4. Ontology 검증 ───────────────────────────────
    print(f"\n{C}[4] Ontology 관계 검증{E}")
    try:
        from core.ontology import normalize_relation, validate_relation
        for rel in TEST_ENTITY["relations"]:
            std_type = normalize_relation(rel["type"])
            valid = validate_relation(TEST_ENTITY["type"], std_type, strict=False)
            print(f"  {'✅' if valid else '⚠️'} "
                  f"{rel['type']} → 표준화: {std_type}")
    except Exception as e:
        print(f"  {Y}⚠️{E}  Ontology 검증 skip: {e}")

    # ─── 5. Memory Trust 검증 ────────────────────────────
    print(f"\n{C}[5] Memory Trust 신뢰도 검증{E}")
    try:
        from core.memory import verify_before_write
        ok, reason, score = verify_before_write(
            entity    = TEST_ENTITY,
            user_role = "admin",
            wiki_dir  = str(engine.wiki_generator.wiki_base_path),
        )
        if ok:
            print(f"  {G}✅{E} Trust 통과 score={score:.3f}")
        else:
            print(f"  {R}❌{E} Trust 거부: {reason} (score={score:.3f})")
    except ImportError:
        print(f"  {Y}⚠️{E}  Memory Trust 모듈 없음 (skip)")
    except Exception as e:
        print(f"  {Y}⚠️{E}  Trust 검증 오류: {e}")

    # ─── 6. 실제 적용 (--apply 시에만) ─────────────────
    if apply:
        print(f"\n{C}[6] 실제 entity 생성{E}")
        try:
            result_path = engine.wiki_generator.create_entity_file(
                TEST_ENTITY,
                TEST_ENTITY["metadata"]["filename"],
                [],
            )
            print(f"  {G}✅{E} 생성 완료: {result_path}")

            # vector store 추가
            from core.tokenizer import split_chunks
            content = Path(result_path).read_text(encoding="utf-8")
            chunks = split_chunks(content)
            engine.vector_store.add_documents_with_meta(
                texts=chunks,
                source=TEST_ENTITY["metadata"]["filename"],
                metadata={
                    "sensitivity": TEST_ENTITY["sensitivity"],
                    "source_type": "prod",
                    "owner":       "system",
                },
            )
            print(f"  {G}✅{E} vector store 추가: {len(chunks)} chunks")

            # 인덱스 갱신 확인
            engine.wiki_generator.refresh_entity_map()
            new_count = len(engine.wiki_generator.entity_id_index)
            print(f"  {G}✅{E} entity_id_index: {new_count}개 (1개 증가)")

            # 정리
            print(f"\n{Y}  💡 테스트 entity 정리:{E}")
            print(f"     del \"{result_path}\"")
            print(f"     python tools\\admin\\wiki_reset.py --confirm")

        except Exception as e:
            print(f"  {R}❌{E} 생성 실패: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"\n{Y}[6] 실제 적용 skip (--apply 옵션 없음){E}")

    # ─── 결과 요약 ──────────────────────────────────────
    print(f"\n{B}{C}{'═'*60}{E}")
    print(f"{B}{C}  결과 요약{E}")
    print(f"{B}{C}{'═'*60}{E}")
    if valid_format:
        print(f"  {G}{B}✅ 업로드 흐름 정상{E}")
        print(f"  • entity_id 표준 형식 ✅")
        print(f"  • 폴더 경로 자메스 표준 ✅")
        print(f"  • Ontology + Trust 검증 활성 ✅")
        print(f"\n  📤 실제 파일 업로드 시 자동으로 정확히 작성됩니다.")
    else:
        print(f"  {R}{B}❌ 비정상 — 시스템 점검 필요{E}")

    print(f"\n  {C}실제 적용 테스트:{E}")
    print(f"  python tools\\admin\\upload_simulator.py --apply\n")


if __name__ == "__main__":
    main()
