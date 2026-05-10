# W1 — 진단 3종 (2026-05-11)

> Phase 8 착수 전 사실확인. 코드 변경 없음, 보고서 only.
> 후속 fix PR 분할안 §4 참조.

## 컨텍스트

사용자 지적 (2026-05-11):
1. 캐릭터 성향에서 상관 trait 가 같이 안 움직이는 경우가 있고, 영향력·연관성이 너무 약해 보인다.
2. 첫 설치 시 엔티티 등 위키가 초기화된 빈 상태인지 점검.
3. 이미지/영상 업로드 시 글자 추출 또는 엔티티 추출이 잘 되는지.

본 보고서는 main + #160(P1) 브랜치 코드를 검토한 사실 확인이다. 수정은
하지 않았으며, 후속 PR 으로 분리해서 진행한다.

---

## ① 캐릭터 correlation/영향력 진단

### 1-A. main 브랜치 (현재 머지된 상태)

`core/character_profile.py` (137 lines, 11 traits)

- `set_trait()` 가 **짝(opponent) 100% flip 만** 적용. 상관관계 그래프 자체가
  **존재하지 않음** — 사용자가 한 trait 를 움직여도 짝 외 다른 trait 는 0
  영향. 사용자 지적이 main 기준이면 100% 정확.
- 영향 받는 짝: A(curiosity↔focus), B(caution↔boldness),
  C(analytical↔intuitive), D(independent↔collaborative).
- E 그룹(security/creativity/empathy) 은 **완전 독립** — 어떻게 변경해도
  서로 영향 X.

### 1-B. P1 브랜치 (#160 — 미머지)

`core/character_profile.py` (286 lines, 16 traits, CORRELATIONS 15 edges, damping=0.3)

- 짝 flip + correlation ripple 둘 다 적용. 구조적으로는 OK.
- **그러나** 사용자 체감 "영향력·연관성 너무 약해 보인다" 의 원인 4가지 식별:

| # | 원인 | 수치 근거 | 심각도 |
|---|------|----------|--------|
| **a** | damping=0.3 이 시각상 약함 | caution 0.5→0.9 (delta=0.4) → risk_tolerance ripple = 0.4 × −0.4 × 0.3 = **−0.048**. 슬라이더 1px 가 0.01 = 사람 눈에는 거의 안 보임 | 🔴 |
| **b** | 15 edges 는 sparse | 16×15=240 directed pair 중 15 등재 (6.25%). 많은 trait 가 incoming 또는 outgoing 0개 | 🔴 |
| **c** | outgoing edge 1개 이하인 trait 多 | focus(1), curiosity(1), intuitive(1), analytical(1), independent(1), conciseness(1) — 변경해도 1개만 같이 움직임 | 🟡 |
| **d** | prompt_modifiers 미반영 trait | 16 trait 중 prompt 영향: caution/curiosity/analytical/empathy/creativity/directness/security/conciseness/optimism/risk_tolerance/patience = **11개**. 미반영 5개: **focus, boldness, intuitive, independent, collaborative**. 이들 변경 시 LLM 응답 변화 없음 | 🟠 |

#### 등재된 15 edges 인접도 (P1 코드 기준)

```
incoming edges (target):
  creativity      ← 3 (curiosity, intuitive, ←via collaborative? no)
  directness      ← 5 (analytical, boldness, independent, conciseness, ...)
  risk_tolerance  ← 2 (caution−, boldness+)
  security        ← 1 (caution+)
  empathy         ← 3 (collaborative, directness−, patience)
  collaborative   ← 1 (empathy)
  patience        ← 1 (focus)
  optimism        ← 1 (creativity)

outgoing edges (source):
  focus(1), curiosity(1), intuitive(1), analytical(1)
  caution(2), boldness(2)
  independent(1), collaborative(1), empathy(1+1=2 양방향)
  conciseness(1), directness(1), creativity(1), patience(1)

incoming/outgoing 0개 trait:
  - 들어오기만(incoming만): creativity, security, risk_tolerance, optimism
  - 나가기만(outgoing만): focus, curiosity, intuitive, analytical, independent, conciseness
  - 양쪽 모두: caution, boldness, collaborative, empathy, directness, patience, creativity (mixed)
```

### 1-C. 권고 (W3 fix PR 에서 처리)

- damping 0.3 → **0.6 또는 trait별 가중치** (일부 강한 상관은 더 강하게).
  사람 눈에 보이려면 ripple ≥ 0.05 가 최소.
- 등재 edges 15 → **30~40 edges** 로 확장. 미반영 trait 의 incoming 보강.
- prompt_modifiers 에 **focus, intuitive, independent, collaborative, boldness**
  directive 추가 — 5개 trait 가 LLM 응답에 직접 영향하도록.
- 별도 항목: radar UI 입체감 — radial gradient + glow + drop-shadow + depth
  filter (W3 의 FE 작업).

---

## ② 첫 설치 위키 빈 상태 진단

### 2-A. tracked wiki 파일 (git ls-files)

| 파일 | 내용 | 첫 설치자에게 |
|---|---|---|
| `wiki/index.md` | `total_entities: 0`, person/concept/org/document = 0 | ✅ 깨끗 |
| `wiki/synonyms.yaml` | 샘플(비트코인/이더리움 등 crypto) — 사용자 데이터 X | ✅ 깨끗 (샘플만) |

### 2-B. .gitignore (line 61~67)

```
wiki/entity/prod/concept/*.md
wiki/entity/prod/org/*.md
wiki/entity/prod/person/*.md
wiki/entity/prod/document/*.md
wiki/entity/prod/system_internal/*.md
```

⚠️ **누수 위험 식별**:

1. **카테고리 한정 패턴** — 위 5개 카테고리 외에 (예: `food/`, `event/`,
   `relation/` 등) 새 카테고리가 추가되면 자동으로 ignored 되지 않음. 즉
   `wiki/entity/prod/food/*.md` 가 만들어지면 그대로 git 에 추적됨.
   → 권고: **`wiki/entity/prod/**/*.md`** wildcard 로 변경 + index.md /
   .gitkeep 같은 메타파일은 명시적 unignore (`!wiki/entity/prod/index.md`).

2. **`wiki/prod/`** 폴더 (entity 없이 prod 직속) — 현재 사용자 로컬에
   untracked 로 존재. .gitignore 에 등재 X. 다른 사용자가 같은 경로에 데이터
   넣고 `git add wiki/prod/` 하면 그대로 들어감. 정확한 의도가
   `wiki/entity/prod/` 와의 별개인지 확인 필요. 의도된 구조면 .gitignore 에
   추가, 아니면 data 위치 통일.

3. **uploads/, chroma_db/, memory/, *.db** ✅ 모두 ignored.

### 2-C. 권고 (W7 또는 별도 hotfix PR)

- .gitignore 패턴 wildcard 화 + 의도 정렬 (`wiki/prod/` vs `wiki/entity/prod/`).
- `scripts/reset_for_production.py` 는 이미 잘 되어 있음 (수동 실행) — 첫
  설치자에게는 불필요하지만 데이터 갱신 시 유용.
- 첫 설치 자동 검증 스크립트 (`scripts/verify_clean_install.py`) 추가 검토:
  index.md.total_entities==0, prod/{*}/ 디렉토리 비어있음, chroma_db
  비어있음 등 자동 검증.

### 2-D. 결론

**첫 설치 시 위키는 사실상 깨끗** (index.md=0, synonyms=샘플만, prod 폴더
ignored). 다만 .gitignore 패턴이 카테고리 한정이라 향후 누수 위험 있음.
긴급도 🟡.

---

## ③ 이미지/영상 OCR + 엔티티 추출 진단

### 3-A. 현재 상태 (`processors/file_processor.py`)

| 형식 | extract 메서드 | trust | 결과 |
|---|---|---|---|
| `txt`, `md` | `extract_text` | medium | ✅ 정상 |
| `pdf` (text-PDF) | MarkItDown | medium | ✅ 정상 |
| `pdf` (스캔 PDF) | OCR fallback (Tesseract+kor+eng) | low | ✅ 정상 |
| `docx`, `xlsx`, `pptx`, `hwp` | MarkItDown | medium | ✅ 정상 |
| **이미지** (`png/jpg/jpeg/bmp/tiff/webp`) | **vision tiling → EasyOCR → Tesseract 3-tier** | low | ✅ 정상 |
| **음성** (`mp3/wav/m4a/ogg`) | **Whisper ASR (base 모델, ko)** | low | ✅ 정상 |
| **영상** (`mp4/avi/mov/mkv`) | **❌ STUB — 처리 안 함** | low | ❌ **"[영상 분석 결과 - 샘플링 기반]" 만 반환** |

### 3-B. 영상 stub 의 영향

`file_processor.py:182-188`:

```python
def extract_video(self, filepath) -> TrustedContent:
    # Stub — 향후 frame ASR + vision caption 합성. 둘 다 low-trust.
    return TrustedContent(
        text="[영상 분석 결과 - 샘플링 기반]",
        source="asr",
        trust="low",
    )
```

→ 영상 업로드 시:
1. 텍스트 추출: **0자** (스텁 라벨만).
2. 엔티티 추출: 위 텍스트로는 entity extractor 가 의미 있는 트리플을
   못 뽑음 → **엔티티 0건**.
3. 벡터 인덱스: stub 텍스트가 ChromaDB 에 들어가서 **노이즈**가 됨.
4. 사용자에게는 "처리 완료" 메시지가 가기 때문에 **silent failure** —
   업로드는 성공, 검색은 안 됨.

### 3-C. 권고 (별도 PR — W7 후 또는 multimodal 트랙)

**Option A — 즉시 단순 fix (1~2일)**:
- 영상 → 음성 트랙 분리 (`ffmpeg -i input.mp4 -vn -ar 16k -ac 1 output.wav`)
  → Whisper 로 transcribe (이미 있는 인프라 활용).
- 프레임 샘플링 (10초 간격) → 각 frame 을 vision tiling 1회 → 캡션 합성.
- 두 결과 concat → entity extractor 통과.
- 의존성: ffmpeg-python (또는 imageio-ffmpeg). 보안: 영상 sandbox 필요 X
  (frame 추출 만), Whisper 는 이미 사용 중.

**Option B — JEPA/V-JEPA 검토 (보류 권고)**:
- V-JEPA 비전모델은 캡션 생성용 아니므로 단순 OCR 대체 불가.
- 임베딩만으로는 entity 추출 X. 별도 vision-language 모델 필요.
- v0.2 hardening 외 신규 의존성 — `docs/design/v0.3-multimodal.md` 메모로
  보류 권고. (#9 와도 연관.)

**Option C — 즉시는 거부 + UI 가이드 (가장 안전, 보수적)**:
- 영상 업로드 시 "현재 영상은 아직 미지원 — `.mp3/.wav/.mp4(audio)` 만
  업로드해 주세요" UI 메시지.
- backend 차원에서도 거부 + 422 응답.
- 후속에 Option A 진행.

#### 추천: **Option C → Option A** (안전 우선)

silent failure 가 가장 큰 위험. 일단 거부로 막고, 후속 PR 에서 ASR+frame
caption 합성 도입.

### 3-D. 결론

이미지 ✅ / 음성 ✅ / **영상 ❌ stub silent failure**.
긴급도 🔴 (사용자 신뢰 손상 + 노이즈 데이터 인덱스 오염).

---

## ④ 후속 fix PR 분할안

진단 결과 → 4개 PR 로 분할 (의존성 없음, 독립 진행 가능):

| PR | 내용 | 의존 | 우선순위 | 비고 |
|---|---|---|---|---|
| **W3a** (FE) | character radar UI 입체감 — radial gradient/glow/depth filter | #160~#163 머지 후 | 🟡 | radar 시각 품질 |
| **W3b** (BE) | character correlation 강화 — damping 0.3→0.6 + trait별 weight + edges 15→30+ + prompt 미반영 trait 5개 보강 | #160~#163 머지 후 | 🔴 | 핵심 영향력 fix |
| **W7-hotfix** | .gitignore 패턴 wildcard 화 + `wiki/prod/` 정리 | — | 🟡 | 누수 예방 |
| **W?-video-reject** | 영상 업로드 거부 + UI 가이드 (Option C) | — | 🔴 | silent failure 차단 |
| **W?-video-asr** | 영상 ASR+frame caption 합성 (Option A) | video-reject 후 | 🟢 | 전체 지원 |

### v1.0 / v0.3 후순위
- V-JEPA / JEPA 비전 모델 — `docs/design/v0.3-multimodal.md` 로 보류
  (Option B). 현재 v0.2 hardening 외 의존성 추가 부담.

---

## 검증 절차 (이 PR 본체)

이 PR 은 보고서 only. 검증:
- [ ] `reports/w1_diagnostics_2026-05-11.md` 가 읽기 좋은지
- [ ] 후속 fix PR 분할안 §4 가 합리적인지
- [ ] 사용자가 W3a/W3b/W7-hotfix/video-reject 중 어디부터 진행할지 결정

코드 변경 없음 → 회귀 위험 0.
