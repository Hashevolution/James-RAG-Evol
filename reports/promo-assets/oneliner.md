# One-liner Copy (v0.4.4 base)

> Source of truth for all promo channels. Update this file first when a release lands; downstream posts (devto / HN / reddit) reference these one-liners.

## 영문

### 기본 (Show HN / awesome list 용)
JAMES — an audit-native local-first Graph-RAG platform with two pre-registered deterministic benchmarks: RAB (Replayable-Audit, EU AI Act Art. 10/12/19) and LRB (Lifecycle Retrieval, temporal validity). v0.4.4, MIT.

### 사실 위주 (Hacker News 제목 라인 후보)
- Show HN: JAMES v0.4.4 – an audit-native Graph-RAG platform with two pre-registered benchmarks (RAB + LRB) operationalising EU AI Act Article 10/12/19
- Show HN: JAMES v0.4.4 – a laptop-runnable Graph-RAG with replayable lifecycle and validity-window time-travel retrieval

### Reddit / 사용자 시점
I built a local-first Graph-RAG that scores its own audit-log quality (AC/RF/PC = 1.0/1.0/1.0 vs vanilla default-logging 0.275/0/0) and preserves R@1 V<N<J on time-travel queries across 4 model families × 4 scale points (12.5× span). Two preprint PDFs + Zenodo DOI shipped. v0.4.4, MIT.

### Twitter / LinkedIn (140자 안쪽)
JAMES v0.4.4 — audit-native Graph-RAG + 2 pre-registered benchmarks (RAB + LRB) anchored to EU AI Act Art. 10/12/19. Local-first. MIT. https://github.com/Hashevolution/James-RAG-Evol

### Enterprise (customer outreach 1줄)
JAMES is a local-first RAG platform whose audit-log quality and temporal-validity retrieval are measured deterministically against EU AI Act Article 10/12/19 record-keeping requirements (applies from 2026-08-02). Two preprint PDFs + Zenodo DOI for citation. MIT.

---

## 한국어

### 기본 (한국 NLP 커뮤니티 용)
JAMES — 로컬-우선 audit-native Graph-RAG 플랫폼. EU AI Act Article 10/12/19 에 verbatim 매핑되는 두 pre-registered 벤치마크 (RAB + LRB) 동봉. v0.4.4, MIT.

### 사실 위주 (geeknews / hada 게시 라인 후보)
- JAMES v0.4.4 — Audit Completeness/Replay Fidelity/Provenance Coverage 결정론적 측정 + validity-window time-travel retrieval. 두 preprint PDF + Zenodo DOI 동봉.
- JAMES v0.4.4 — RAG audit log 품질을 EU AI Act 조항에 직접 매핑한 두 벤치마크 (RAB + LRB) 출시. 로컬 동작, MIT.

### Twitter / LinkedIn 한글 (140자 안쪽)
JAMES v0.4.4 — audit-native Graph-RAG + 2 pre-registered 벤치마크 (RAB + LRB). EU AI Act 직결 측정. 로컬 동작, Ollama 기반. MIT. https://github.com/Hashevolution/James-RAG-Evol

---

## 핵심 facts (모든 라인의 backing)

| Surface | Value |
|---|---|
| Current version | v0.4.4 (2026-06-12) |
| DOI | [10.5281/zenodo.20652679](https://doi.org/10.5281/zenodo.20652679) |
| Preprints | RAB 10pg + LRB 11pg ([papers/](https://github.com/Hashevolution/James-RAG-Evol/tree/main/papers)) |
| RAB headline | AC/RF/PC = 1.000/1.000/1.000 vs Baseline-0 (vanilla default-logging) = 0.275/0/0 on scenario-S1 |
| LRB headline | R@1 V<N<J preserved across 4 model families × 4 scale points (12.5× scale span); S3 publication V/N/J = 0.502/0.721/0.845 |
| EU AI Act anchor | RAB 3 metrics map verbatim to Articles 10, 12, 19 (apply from 2026-08-02 per Art. 113) |
| OpenSSF Best Practices | Passing badge |
| License | MIT |
| Local stack | Ollama (gemma4:e4b default) + BAAI/bge-m3 embedder + ChromaDB |
| Test suite | ~200+ benchmark + lifecycle tests; ruff F-class clean |
