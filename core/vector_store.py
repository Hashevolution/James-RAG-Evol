"""
PROJECT JAMES - Vector Store Module

수정 사항:
  Fix 1. self.model 정의 후 미사용 → 모든 임베딩을 self.model로 통일
          (저장/검색 모델 불일치 해소)
  Fix 2. add_documents에 embeddings 파라미터 추가
  Fix 3. search()를 query_embeddings 방식으로 전환
  Fix 4. 모델 로딩 실패 시 fallback (HuggingFace 다운로드)
"""
import chromadb
from sentence_transformers import SentenceTransformer
import uuid
import os
from config import (
    BASE_DIR,
    CHROMA_COLLECTION,
    CHROMA_DIR,
    EMBEDDING_MODEL,
    _embedding_short_name,
)

# ✅ 싱글톤 모델 캐싱 (초기화 10초 → 최초 1회만)
_MODEL_CACHE: dict = {}

# v0.4 Sprint 4 BL-9 prep — derive local-cache path + chroma directory
# from the configured embedding model. The legacy MiniLM tag stays
# mapped to the preexisting `models/miniLM` + `chroma_db` paths so any
# operator who hasn't set `JAMES_EMBEDDING_MODEL` sees zero file-layout
# change. New models get isolated `models/<short>` + `chroma_db_<short>`
# directories.
_LEGACY_MINILM_TAG = "paraphrase-multilingual-MiniLM-L12-v2"

if EMBEDDING_MODEL == _LEGACY_MINILM_TAG:
    _DEFAULT_MODEL_DIR = os.path.join(BASE_DIR, "models", "miniLM")
else:
    _DEFAULT_MODEL_DIR = os.path.join(
        BASE_DIR, "models", _embedding_short_name(EMBEDDING_MODEL),
    )

LOCAL_MODEL_PATH = os.environ.get("JAMES_MODEL_PATH", _DEFAULT_MODEL_DIR)
FALLBACK_MODEL   = EMBEDDING_MODEL


def _chroma_dir_for_model(base_chroma_dir: str) -> str:
    """Per-model chroma directory resolver.

    Returns ``base_chroma_dir`` unchanged when the legacy MiniLM tag
    is configured (so existing operators keep reading from the
    preexisting `chroma_db/`). For any other embedding model, returns
    ``f"{base}_{short}"`` so a swap doesn't clobber the legacy
    embeddings (cosine search requires matching dimensions; mixing
    384-dim MiniLM and 1024-dim bge-m3 in one collection would
    silently corrupt results).
    """
    if EMBEDDING_MODEL == _LEGACY_MINILM_TAG:
        return base_chroma_dir
    suffix = _embedding_short_name(EMBEDDING_MODEL)
    return f"{base_chroma_dir}_{suffix}"


class VectorStore:
    def __init__(self, base_dir=None):
        # v0.4 Sprint 4 BL-9 prep — db_path resolution routes through
        # `_chroma_dir_for_model`. Legacy MiniLM tag → unchanged
        # `chroma_db/` (or `<base_dir>/chroma_db`). New models →
        # per-model `chroma_db_<short>/`.
        legacy_base = os.path.join(base_dir, "chroma_db") if base_dir else CHROMA_DIR
        self.db_path = _chroma_dir_for_model(legacy_base)
        os.makedirs(self.db_path, exist_ok=True)
        print(f"[VECTOR_STORE] ChromaDB 경로: {self.db_path}")
        if EMBEDDING_MODEL != _LEGACY_MINILM_TAG:
            print(f"[VECTOR_STORE] 임베딩 모델: {EMBEDDING_MODEL} (per-model chroma dir)")

        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )

        # Fix 4: 로컬 모델 → 실패 시 HuggingFace fallback
        self.model = self._load_model()
        print("[VECTOR_STORE] VectorStore 초기화 완료")

    def _load_model(self) -> SentenceTransformer:
        """
        로컬 모델 우선 → HuggingFace fallback (방법 B)
        싱글톤 캐싱으로 초기화 10초 → 최초 1회만 로딩
        """
        global _MODEL_CACHE

        # 캐시 히트 → 즉시 반환
        if "model" in _MODEL_CACHE:
            print("[VECTOR_STORE] 모델 캐시 히트 (재로딩 없음)")
            return _MODEL_CACHE["model"]

        model = None

        # 1순위: 로컬 모델
        if os.path.exists(LOCAL_MODEL_PATH):
            try:
                model = SentenceTransformer(LOCAL_MODEL_PATH, local_files_only=True)
                print(f"[VECTOR_STORE] 로컬 모델 로드 성공: {LOCAL_MODEL_PATH}")
            except Exception as e:
                print(f"[VECTOR_STORE] 로컬 모델 실패 ({e}) → HuggingFace fallback")

        # 2순위: HuggingFace 자동 다운로드 (방법 B — 개발 중 허용)
        if model is None:
            print(f"[VECTOR_STORE] HuggingFace fallback: {FALLBACK_MODEL}")
            try:
                model = SentenceTransformer(FALLBACK_MODEL)
                # 로컬 저장 (다음 실행부터 로컬 모델로 사용)
                os.makedirs(LOCAL_MODEL_PATH, exist_ok=True)
                model.save(LOCAL_MODEL_PATH)
                print(f"[VECTOR_STORE] 로컬 저장 완료: {LOCAL_MODEL_PATH}")
            except Exception as e:
                print(f"[VECTOR_STORE] HuggingFace 다운로드 실패: {e}")
                raise RuntimeError("임베딩 모델 로드 실패") from e

        _MODEL_CACHE["model"] = model
        return model

    def _embed(self, texts: list) -> list:
        """Fix 1: self.model로 임베딩 통일"""
        if isinstance(texts, str):
            texts = [texts]
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    # ─────────────────────────────────────
    # Fix 2: add_documents — embeddings 포함
    # ─────────────────────────────────────

    def add_documents(self, texts: list, source: str):
        if not texts:
            print("[VECTOR_STORE] 저장할 텍스트 없음")
            return

        print(f"[VECTOR_STORE] 저장 시작: {source} ({len(texts)}개)")
        ids        = [str(uuid.uuid4()) for _ in texts]
        metadatas  = [{"source": source} for _ in texts]
        embeddings = self._embed(texts)   # Fix 2

        try:
            self.collection.add(
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            print(f"[VECTOR_STORE] 저장 완료: {len(texts)} chunks")
        except Exception as e:
            print(f"[VECTOR_STORE] Chroma 저장 실패: {e}")

    # ─────────────────────────────────────
    # Fix 3: search — query_embeddings 방식
    # ─────────────────────────────────────

    def search(
        self,
        query:       str,
        top_k:       int            = 5,
        source_type: str | None     = None,   # [P4.5-2] 'prod' / 'test' / None
    ) -> list:
        """
        [P4.5-2] source_type 필터 지원.
        source_type='prod' → 프로덕션 데이터만 검색 (테스트 오염 방지)
        source_type=None   → 전체 검색
        """
        print(f"[VECTOR_STORE] 검색: {query[:60]} (src={source_type})")
        try:
            q_emb   = self._embed([query])
            results = self.collection.query(
                query_embeddings=q_emb,
                n_results=min(top_k, max(self.collection.count(), 1)),
                include=["documents", "metadatas", "distances"]
            )

            docs   = results.get("documents",  [[]])[0]
            metas  = results.get("metadatas",  [[]])[0]
            dists  = results.get("distances",  [[]])[0]

            output = []
            for doc, meta, dist in zip(docs, metas, dists):
                # [P4.5-2] source_type 필터 적용
                if source_type:
                    doc_src = meta.get("source_type", "prod")
                    if doc_src != source_type:
                        continue

                score = 1 / (1 + dist) if dist is not None else 0
                output.append({
                    "text":     doc,
                    "source":   meta.get("source", "unknown"),
                    "score":    score,
                    "metadata": meta,
                })

            print(f"[VECTOR_STORE] 결과: {len(output)}개")
            return output

        except Exception as e:
            print(f"[VECTOR_STORE] 검색 실패: {e}")
            return []

    # ─────────────────────────────────────
    # ABAC 메타데이터 포함 저장
    # ─────────────────────────────────────

    def add_documents_with_meta(self, texts: list, source: str, metadata: dict = None):
        """
        ABAC 메타데이터 포함 저장.
        [P4.5-2] source_type (prod/test) 함께 저장 → 검색 시 필터 가능.
        """
        if not texts:
            return
        if metadata is None:
            metadata = {}

        self.delete_by_source(source)

        base_meta = {
            "source":      source,
            "sensitivity": metadata.get("sensitivity", "internal"),
            "owner":       metadata.get("owner", "system"),
            "category":    metadata.get("category", "기타"),
            # [P4.5-2] source_type 저장
            "source_type": metadata.get("source_type", "prod"),
        }
        ids        = [str(uuid.uuid4()) for _ in texts]
        metadatas  = [dict(base_meta) for _ in texts]
        embeddings = self._embed(texts)

        try:
            self.collection.add(
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            print(f"[VECTOR_STORE] ABAC 저장 완료: {source} ({len(texts)} chunks, src={base_meta['source_type']})")
        except Exception as e:
            print(f"[VECTOR_STORE] 저장 실패: {e}")

    def delete_by_source(self, source: str) -> bool:
        try:
            existing = self.collection.get(where={"source": source})
            if existing and existing["ids"]:
                self.collection.delete(ids=existing["ids"])
                print(f"[VECTOR_STORE] 삭제: {source} ({len(existing['ids'])}개)")
                return True
        except Exception as e:
            print(f"[VECTOR_STORE] 삭제 실패: {e}")
        return False

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception as e:
            print(f"[VECTOR_STORE] 카운트 실패: {e}")
            return -1
