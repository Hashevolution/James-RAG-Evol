"""
PROJECT JAMES — Wiki/DB 안전 리셋 도구

사용자 결정 (옵션 B + A + C):
  ✅ wiki/ 디렉토리 비우기
  ✅ chroma_db/ 임베딩 비우기
  ✅ memory DB 비우기 (대화/페르소나/preferences)
  ✅ audit log 초기화
  ✅ test 폴더 폐기 (prod만 유지)
  ✅ 시드 데이터 5~10개 자동 생성

사용:
  python tools/admin/wiki_reset.py --dry-run     # 영향 범위만 표시
  python tools/admin/wiki_reset.py --confirm     # 실제 실행
  python tools/admin/wiki_reset.py --confirm --no-seed   # 시드 제외
  python tools/admin/wiki_reset.py --seed-only   # 리셋 안 하고 시드만
"""

import os
import sys
import shutil
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# config 경로 로드
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# Issue #2: cp949 콘솔에서 box-drawing 문자(`═`, `─` …) 출력 시
# UnicodeEncodeError 크래시 방지. 모든 print 전에 stdout 인코딩 강제.
from utils.console import ensure_utf8_console
ensure_utf8_console()

try:
    from config import BASE_DIR, WIKI_DIR, CHROMA_DIR
except ImportError:
    # tools/admin/ 위치 → 두 단계 위가 프로젝트 루트
    BASE_DIR   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    WIKI_DIR   = os.path.join(BASE_DIR, "wiki")
    CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")

MEMORY_DB     = Path(BASE_DIR) / "memory" / "james_memory.db"
AUDIT_DB      = Path(BASE_DIR) / "audit" / "james_audit.db"
AUDIT_LOGS    = [
    Path(BASE_DIR) / "james_audit_db.jsonl",
    Path(BASE_DIR) / "james_attack_log.jsonl",
    Path(BASE_DIR) / "james_evo_log.jsonl",
    Path(BASE_DIR) / "james_multimodal_log.jsonl",
]
WORKSPACE_DIR  = Path(BASE_DIR) / "workspace"
ENTITY_INDEX   = Path(BASE_DIR) / "entity_id_index.json"

# 색상
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"
B = "\033[1m";  E = "\033[0m"


def banner(title: str):
    print(f"\n{B}{C}{'═'*60}{E}")
    print(f"{B}{C}  {title}{E}")
    print(f"{B}{C}{'═'*60}{E}\n")


def confirm(msg: str) -> bool:
    """Y/N 인터랙티브 확인"""
    ans = input(f"{Y}❓ {msg} [y/N]: {E}").strip().lower()
    return ans in ("y", "yes")


# ──────────────────────────────────────────────────
# 1. 영향 범위 분석 (dry-run)
# ──────────────────────────────────────────────────

def analyze_impact() -> dict:
    """삭제 대상 분석. 실제 삭제는 안 함."""
    impact = {
        "wiki_files":     [],
        "chroma_size":    0,
        "memory_size":    0,
        "audit_logs":     [],
        "workspace":      [],
        "entity_index":   None,
    }

    # wiki 파일 카운트
    wiki = Path(WIKI_DIR)
    if wiki.exists():
        impact["wiki_files"] = [p for p in wiki.rglob("*.md")]
        impact["wiki_subdirs"] = [d for d in wiki.iterdir() if d.is_dir()]

    # chroma_db 크기
    chroma = Path(CHROMA_DIR)
    if chroma.exists():
        size = sum(f.stat().st_size for f in chroma.rglob("*") if f.is_file())
        impact["chroma_size"] = size

    # memory DB
    if MEMORY_DB.exists():
        impact["memory_size"] = MEMORY_DB.stat().st_size

    # audit logs
    for f in AUDIT_LOGS:
        if f.exists():
            impact["audit_logs"].append((f, f.stat().st_size))
    if AUDIT_DB.exists():
        impact["audit_logs"].append((AUDIT_DB, AUDIT_DB.stat().st_size))

    # workspace
    if WORKSPACE_DIR.exists():
        impact["workspace"] = [
            p for p in WORKSPACE_DIR.iterdir()
            if p.is_file() and p.suffix in (".jsonl", ".json", ".db")
        ]

    # entity_id_index
    if ENTITY_INDEX.exists():
        impact["entity_index"] = ENTITY_INDEX.stat().st_size

    return impact


def print_impact(impact: dict):
    """영향 범위 출력."""
    print(f"  {C}📁 wiki 파일{E}      : {len(impact['wiki_files'])}개")
    if impact.get("wiki_subdirs"):
        for d in impact["wiki_subdirs"]:
            md_count = len(list(d.rglob("*.md")))
            print(f"      └─ {d.name}/  ({md_count}개 .md)")

    chroma_mb = impact["chroma_size"] / 1024 / 1024
    print(f"  {C}🗄️  chroma_db{E}     : {chroma_mb:.1f} MB")

    mem_kb = impact["memory_size"] / 1024
    print(f"  {C}🧠 memory.db{E}     : {mem_kb:.1f} KB")

    print(f"  {C}📋 audit 로그{E}    : {len(impact['audit_logs'])}개 파일")
    for f, size in impact["audit_logs"]:
        print(f"      └─ {f.name} ({size//1024} KB)")

    print(f"  {C}⚙️  workspace{E}    : {len(impact['workspace'])}개 파일")
    print(f"  {C}🔗 entity_index{E}  : "
          f"{'있음' if impact['entity_index'] else '없음'}")


# ──────────────────────────────────────────────────
# 2. 실제 리셋 실행
# ──────────────────────────────────────────────────

def reset_wiki():
    """wiki 폴더 비우기 + 자메스 표준 구조로 재생성."""
    wiki = Path(WIKI_DIR)
    if wiki.exists():
        shutil.rmtree(wiki)
        print(f"  {G}✅{E} wiki/ 삭제됨")
    # 자메스 표준 구조: wiki/entity/{source_type}/{type}/
    structure = [
        wiki / "entity" / "prod" / "person",
        wiki / "entity" / "prod" / "org",
        wiki / "entity" / "prod" / "concept",
        wiki / "entity" / "prod" / "document",
    ]
    for d in structure:
        d.mkdir(parents=True, exist_ok=True)
    print(f"  {G}✅{E} wiki/entity/prod/ 폴더 구조 재생성 (자메스 표준)")


def reset_chroma():
    """chroma_db 임베딩 삭제."""
    chroma = Path(CHROMA_DIR)
    if chroma.exists():
        shutil.rmtree(chroma)
        print(f"  {G}✅{E} chroma_db/ 삭제됨")
    chroma.mkdir(parents=True, exist_ok=True)
    print(f"  {G}✅{E} chroma_db/ 빈 폴더 재생성")


def reset_memory():
    """memory DB 초기화 (테이블 구조는 유지, 데이터만 삭제)."""
    if not MEMORY_DB.exists():
        print(f"  {Y}⚠️{E}  memory.db 없음 — 새로 생성됨 (서버 시작 시)")
        return
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        # 테이블 목록 조회
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall() if not r[0].startswith("sqlite_")]
        # 모든 테이블 비우기 (스키마 유지)
        for t in tables:
            cursor.execute(f"DELETE FROM {t}")
        conn.commit()
        conn.close()
        print(f"  {G}✅{E} memory.db 데이터 삭제 ({len(tables)}개 테이블)")
    except Exception as e:
        print(f"  {R}❌{E} memory.db 초기화 실패: {e}")


def reset_audit():
    """audit 로그 + DB 초기화."""
    cleared = 0
    for f in AUDIT_LOGS:
        if f.exists():
            f.unlink()
            cleared += 1
    if AUDIT_DB.exists():
        try:
            conn = sqlite3.connect(AUDIT_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall() if not r[0].startswith("sqlite_")]
            for t in tables:
                cursor.execute(f"DELETE FROM {t}")
            conn.commit()
            conn.close()
            cleared += 1
        except Exception:
            pass
    print(f"  {G}✅{E} audit 로그 {cleared}개 초기화")


def reset_workspace():
    """workspace의 학습/평가 로그 초기화 (proposals 보고서 포함)."""
    if not WORKSPACE_DIR.exists():
        return
    cleared = 0
    target_files = [
        "feedback_shadow.jsonl", "feedback_applied.jsonl",
        "importance_log.jsonl", "eval_log.jsonl",
        "screen_agent_log.jsonl", "e2e_report.json",
    ]
    target_dirs = ["proposals", "evo_reports"]

    for name in target_files:
        f = WORKSPACE_DIR / name
        if f.exists():
            f.unlink()
            cleared += 1

    for d_name in target_dirs:
        d = WORKSPACE_DIR / d_name
        if d.exists():
            shutil.rmtree(d)
            d.mkdir(parents=True, exist_ok=True)
            cleared += 1

    print(f"  {G}✅{E} workspace 로그/제안 {cleared}개 초기화")


def reset_entity_index():
    """entity_id_index.json 초기화."""
    if ENTITY_INDEX.exists():
        ENTITY_INDEX.unlink()
        print(f"  {G}✅{E} entity_id_index.json 삭제")
    else:
        print(f"  {Y}⚠️{E}  entity_id_index.json 없음 — 시드 후 자동 재생성")


# ──────────────────────────────────────────────────
# 3. 시드 데이터 생성
# ──────────────────────────────────────────────────

def create_seed_data():
    """시드 데이터 8개 entity 생성 (인물, 조직, 개념 혼합)."""
    print(f"\n{C}  📦 시드 데이터 생성 중...{E}")

    try:
        from tools.admin.seed_data import SEED_ENTITIES, write_seed_files
        count = write_seed_files()
        print(f"  {G}✅{E} 시드 entity {count}개 생성 완료")
    except ImportError:
        # seed_data 모듈이 없으면 inline 시드 사용
        from inline_seed import write_inline_seeds
        count = write_inline_seeds()
        print(f"  {G}✅{E} 시드 entity {count}개 생성 (inline)")
    except Exception as e:
        print(f"  {R}❌{E} 시드 생성 실패: {e}")


def reindex_seeds():
    """시드 데이터 vector 인덱싱 + entity_id_index 갱신."""
    try:
        # 1. RAGEngine 로드 (다중 fallback)
        try:
            from core.graph_rag_engine import RAGEngine
        except ModuleNotFoundError:
            try:
                from graph_rag_engine import RAGEngine
            except ModuleNotFoundError:
                import sys
                sys.path.insert(0, BASE_DIR)
                from core.graph_rag_engine import RAGEngine

        # 2. tokenizer (다중 fallback)
        split_chunks = None
        for module_path in ["core.tokenizer", "tokenizer", "utils.tokenizer"]:
            try:
                mod = __import__(module_path, fromlist=["split_chunks"])
                split_chunks = getattr(mod, "split_chunks", None)
                if split_chunks:
                    break
            except (ImportError, ModuleNotFoundError):
                continue

        # tokenizer 없으면 단순 분할 fallback
        if split_chunks is None:
            print(f"  {Y}⚠️{E}  tokenizer 모듈 없음 — 단순 분할 사용")
            def split_chunks(text, max_chars=1000):
                # ##/### 헤딩 단위 또는 문장 단위 분할
                import re
                sections = re.split(r'\n(?=##\s)', text)
                chunks = []
                for s in sections:
                    s = s.strip()
                    if len(s) > 50:
                        if len(s) <= max_chars:
                            chunks.append(s)
                        else:
                            # 너무 길면 더 잘게
                            for i in range(0, len(s), max_chars):
                                chunks.append(s[i:i+max_chars])
                return chunks if chunks else [text[:max_chars]]

        # 3. 인덱싱 실행
        engine = RAGEngine(default_role="admin")
        wiki = Path(WIKI_DIR)
        indexed = 0
        failed = 0

        for md_file in wiki.rglob("*.md"):
            # 자기 인식 wiki는 시스템 폴더에 별도로 있으므로 entity 폴더만
            if "entity" not in md_file.parts:
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                chunks = split_chunks(content)
                if not chunks:
                    continue

                # frontmatter sensitivity 추출
                import re as _re
                sens_match = _re.search(r'sensitivity:\s*(\w+)', content)
                sensitivity = sens_match.group(1) if sens_match else "internal"

                engine.vector_store.add_documents_with_meta(
                    texts=chunks,
                    source=md_file.name,
                    metadata={
                        "sensitivity": sensitivity,
                        "source_type": "prod",
                        "owner":       "system",
                    }
                )
                indexed += 1
                print(f"      ✓ {md_file.name} ({len(chunks)} chunks)")
            except Exception as e:
                failed += 1
                print(f"      {R}❌{E} {md_file.name}: {e}")

        # 4. entity_id_index 갱신 (Graph 추론에 필수)
        try:
            engine.wiki_generator.refresh_entity_map()
            idx_count = len(engine.wiki_generator.entity_id_index)
            print(f"  {G}✅{E} entity_id_index 갱신: {idx_count}개")
        except Exception as e:
            print(f"  {Y}⚠️{E}  entity_id_index 갱신 실패: {e}")

        print(f"  {G}✅{E} {indexed}개 entity 인덱싱 완료 ({failed}개 실패)")

        if indexed == 0:
            print(f"  {R}❌{E} 인덱싱된 entity 0개 — 다음 확인:")
            print(f"     1) wiki/prod/entity/ 아래 .md 파일 존재 여부")
            print(f"     2) 서버를 끄고 실행했는지 (실행 중이면 lock)")

    except Exception as e:
        print(f"  {R}❌{E} 인덱싱 실패: {e}")
        import traceback
        traceback.print_exc()


# ──────────────────────────────────────────────────
# 메인 워크플로
# ──────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    dry_run     = "--dry-run" in args
    confirmed   = "--confirm" in args
    no_seed     = "--no-seed" in args
    seed_only   = "--seed-only" in args

    if not (dry_run or confirmed or seed_only):
        print(f"\n{Y}사용법:{E}")
        print(f"  python wiki_reset.py --dry-run     # 영향 범위 확인")
        print(f"  python wiki_reset.py --confirm     # 리셋 + 시드 생성")
        print(f"  python wiki_reset.py --confirm --no-seed  # 리셋만")
        print(f"  python wiki_reset.py --seed-only   # 시드만 추가\n")
        return

    # ─── dry-run 모드 ───
    if dry_run:
        banner("📊 영향 범위 분석 (DRY-RUN)")
        impact = analyze_impact()
        print_impact(impact)
        print(f"\n{Y}  실제 리셋: --confirm 옵션으로 실행하세요{E}\n")
        return

    # ─── seed-only 모드 ───
    if seed_only:
        banner("🌱 시드 데이터만 생성")
        create_seed_data()
        reindex_seeds()
        return

    # ─── 실제 리셋 ───
    banner("⚠️  데이터 리셋 시작")

    # 서버 실행 중이면 ChromaDB lock 충돌
    print(f"{Y}  ⚠️  서버가 실행 중이면 먼저 종료하세요 (Ctrl+C){E}")
    print(f"{Y}     ChromaDB 파일 lock으로 인해 인덱싱이 실패할 수 있습니다{E}\n")

    impact = analyze_impact()
    print(f"{Y}  다음 데이터가 삭제됩니다:{E}")
    print_impact(impact)
    print()

    if not confirm("정말로 모든 데이터를 리셋하시겠습니까?"):
        print(f"{Y}  취소됨{E}\n")
        return

    print()
    print(f"{C}  🔥 리셋 실행 중...{E}\n")

    reset_wiki()
    reset_chroma()
    reset_memory()
    reset_audit()
    reset_workspace()
    reset_entity_index()

    print(f"\n{G}{B}  ✅ 리셋 완료{E}")

    # 시드 생성 + 즉시 인덱싱
    if not no_seed:
        if confirm("\n시드 데이터(8개 entity)를 생성하시겠습니까?"):
            create_seed_data()
            print(f"\n{C}  🔄 vector 인덱싱 자동 실행...{E}")
            reindex_seeds()   # ⚡ 시드 생성 후 즉시 인덱싱

    print(f"\n{B}{G}  🎉 모든 작업 완료{E}")
    print(f"\n{C}  다음 단계:{E}")
    print(f"  1. 서버 재시작:  python server_llmwiki.py")
    print(f"     → [INDEX] 8 entities loaded 가 보여야 정상")
    print(f"  2. 챗 확인:      http://localhost:8000")
    print(f"  3. 데이터 확인:  '김민준은 누구야?' 같은 질문\n")


if __name__ == "__main__":
    main()
