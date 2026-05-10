# [임시명세서 초안] STAGE 4B — Trace Correlation via ContextVar + Pre-supplied trace_id

> 본 문서는 STAGE 4B (점수 2/5, 신규 후보 D) 임시명세서 작성을 위한 skeleton입니다.
> 특허로(patent.go.kr) 전자출원 시 본 문서를 기반으로 PDF·hwp로 전환하여 첨부하십시오.
> 작성 시 [TODO] 마커를 모두 제거·채워주세요.
>
> ⚠️ 점수 2/5 — 비용 압박 시 가장 먼저 생략 검토 후보. STAGE 1/1B 종속항 흡수도 가능.
>
> **참고 자료**: PR #67 (ContextVar 인프라), PR #97 (real reasoning stream), PR #138 (3D reasoning-graph visualizer). `core/observability.py` (**Phase 1 구현 완료** — uuid7 trace_id 발급, contextvars 기반 전파, 245줄, 메인 머지 완료), `frontend/static/chat.js:1346-1542`, `server_llmwiki.py /trace/poll/{trace_id}`.

---

## 발명의 명칭
**클라이언트 사전 송신 trace_id 와 ContextVar 전파를 이용한 실시간 UI 동기화 방법 및 시스템**
(영문: Real-time UI Synchronization via Client-Pre-supplied trace_id and ContextVar Propagation)

## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]

## 공지예외 주장
- 공개일자: [TODO: PR #67 commit 일자 확인 후 기재]
- 공개매체: GitHub public repository (https://github.com/Hashevolution/James-RAG-Evol)
- 공개주체: 발명자 본인
- 공지예외 만료일: [TODO: 공개일자 + 12개월]
- 증빙: `docs/patent/disclosure_log.txt` (D 후보 항목)

---

## 1. 기술 분야

본 발명은 분산 추적(distributed tracing) 시스템에 관한 것으로, 보다 구체적으로는 LLM 기반 채팅 시스템에서 클라이언트가 사전 생성한 trace_id를 서버에 송신하고 동일 trace_id로 stage event를 폴링하여 서버 응답이 도착하기 전에 UI를 실시간으로 동기화하는 방법 및 시스템에 관한 것이다.

## 2. 배경 기술

### 2.1 기존 distributed tracing 시스템의 한계

OpenTelemetry, Datadog APM, Jaeger 등 기존 distributed tracing 시스템은 trace를 **사후 분석(post-mortem analysis)** 용으로 설계됐다. 즉:
- trace_id는 서버가 생성하여 응답 헤더로 클라이언트에 전달
- 클라이언트는 응답을 받은 후에야 trace_id를 알게 됨
- trace event는 백엔드 모니터링 도구로만 조회 가능, 사용자 UI에는 노출되지 않음

### 2.2 LLM 채팅 UI의 progress 표시 한계

ChatGPT 류 LLM 채팅 UI는 응답 생성 중 "thinking..." progress를 표시하지만 다음 한계를 가진다:
- (i) Timer-based 애니메이션이 대부분 — 실제 서버 진행과 무관
- (ii) Stage 정보(검색 → 추론 → 출력 등) 노출 부재
- (iii) 서버 streaming response를 사용해도 "어느 단계인지" 정밀하게 알기 어려움
- (iv) 응답 도착 전 폴링 시 race condition 발생 — 서버가 trace_id를 발급하기 전에 클라이언트가 폴링하면 미스

### 2.3 본 발명이 다루는 시나리오

사용자가 LLM 챗봇에 복잡한 query를 던지면 서버는 다음 stage들을 순차 수행: (1) entity extraction → (2) hybrid search → (3) graph DFS → (4) memory loom → (5) LLM generation. 각 stage는 0.3~5초 소요. 사용자는 응답을 기다리는 동안 "지금 어느 단계인지" 시각적으로 알고 싶다.

기존 시스템은:
- (a) timer 애니메이션만 — 실제 stage와 무동기
- (b) SSE/WebSocket streaming — race-free 보장 어려움, 서버 인프라 부담
- (c) 사후 trace 조회 — 응답 도착 후에야 stage 정보 표시 가능

## 3. 해결하고자 하는 과제

1. 클라이언트가 응답 전에 미리 stage event를 polling 가능하도록 trace_id를 사전 송신하는 메커니즘
2. 서버 응답 전 polling 시작에서 발생하는 race condition을 회피하는 방법
3. 다중 모듈에 걸친 stage event를 동일 trace_id로 cross-module 전파하는 ContextVar 활용 방법
4. UI 애니메이션을 timer가 아닌 실제 서버 stage 진행에 동기화하는 방법

## 4. 과제의 해결 수단

### 4.1 클라이언트 사전 trace_id 생성 + 송신

기존 패턴 (서버가 trace_id 발급):
```
[Client] POST /chat (no trace_id)
[Server] generate trace_id, return in response header
[Client] now knows trace_id, can poll
```

본 발명 패턴 (클라이언트가 trace_id 생성):
```
[Client] generate trace_id_C (UUIDv4), POST /chat with body {trace_id: trace_id_C}
[Client] immediately start polling /trace/poll/{trace_id_C}
[Server] receives POST, sets ContextVar(trace_id) = trace_id_C
[Server] every stage logs event(trace_id_C, stage_name, ts)
[Client] polling sees stage events as they accumulate
[Server] completes, returns response
[Client] stop polling on response receipt
```

### 4.2 ContextVar 전파 (Cross-module)

서버 entry point에서 ContextVar를 설정해 모든 downstream 모듈이 동일 trace_id로 stage event 기록:

```python
# core/observability.py
import contextvars

_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")

def start_trace(trace_id: str):
    """서버 entry point에서 호출. 이후 모든 호출이 trace_id 컨텍스트에 들어감."""
    _TRACE_ID.set(trace_id)

def log_stage(stage: str, payload: dict):
    """모듈 어디서든 호출. ContextVar로 trace_id 자동 획득."""
    tid = _TRACE_ID.get()
    if not tid: return
    _store_event(tid, stage, payload, ts=datetime.now())

# server_llmwiki.py:chat endpoint
@app.post("/chat")
async def chat(req: ChatRequest):
    start_trace(req.trace_id)        # 클라이언트가 송신한 ID로 컨텍스트 시작
    ...
    log_stage("entity_extraction", {...})    # 모든 downstream 호출이 같은 trace_id 사용
    ...
```

### 4.3 Race-free Polling Endpoint

```python
# server_llmwiki.py
@app.get("/trace/poll/{trace_id}")
async def poll_trace(trace_id: str, since: int = 0):
    """
    클라이언트가 응답 전부터 폴링 가능.
    응답 도착 전이라도 누적된 stage event 반환.
    """
    events = _events_for(trace_id, since)
    return {"events": events, "next_since": ...}
```

핵심: 서버는 trace_id를 받자마자 (POST `/chat` body parsing 직후, 비즈니스 로직 진입 전에) **immediately** ContextVar 설정 + event store 초기화. 따라서 클라이언트 polling 도착 시 이미 store가 준비되어 있어 race-free.

### 4.4 클라이언트 UI 동기화 (`frontend/static/chat.js:1346-1542`)

```javascript
async function sendQuery(text) {
  const traceId = crypto.randomUUID();      // 클라이언트가 사전 생성

  // 1. 폴링 즉시 시작 (서버 응답 기다리지 않음)
  let lastSince = 0;
  const pollHandle = setInterval(async () => {
    const r = await fetch(`/trace/poll/${traceId}?since=${lastSince}`);
    const j = await r.json();
    for (const ev of j.events) {
      updateUIStage(ev.stage, ev.payload);   // UI 애니메이션 stage 진척
    }
    lastSince = j.next_since;
  }, 200);

  // 2. POST /chat 송신 (trace_id 포함)
  const res = await fetch("/chat", {
    method: "POST",
    body: JSON.stringify({text, trace_id: traceId}),
  });
  const data = await res.json();

  // 3. 응답 도착 → 폴링 중단
  clearInterval(pollHandle);
  showFinalAnswer(data.answer);
}
```

### 4.5 Stage Event 시간 정확도

각 stage event는 timestamp (`ts`) 와 stage name, payload (관련 메트릭) 를 포함:
- `entity_extraction` — `{tokens: 12, elapsed_ms: 280}`
- `hybrid_search` — `{docs_found: 8, top_score: 0.91}`
- `graph_dfs` — `{nodes_visited: 24, max_depth: 4}`
- `memory_loom` — `{candidates: 3, accepted: 1}`
- `llm_generation` — `{tokens_in: 450, tokens_out: 78}`

UI는 이 메트릭을 해석해 progress bar + 단계명 + 부수 정보를 동기화 표시.

## 5. 효과

1. **응답 전 progress 표시** — 클라이언트 polling이 서버 응답 전부터 stage 정보 수신
2. **Race-free** — ContextVar 즉시 초기화로 polling이 미스되지 않음
3. **Cross-module trace 일관성** — 모든 모듈이 동일 trace_id로 event 기록, 사후 디버깅 용이
4. **인프라 부담 최소** — WebSocket·SSE 불필요, REST polling만으로 동작
5. **사용자 신뢰 향상** — UI가 timer가 아닌 실제 진행에 동기화 → "응답이 멈췄나?" 의심 감소

## 6. 청구범위

### 청구항 1 (방법 — UI 동기화)

LLM 기반 채팅 시스템의 실시간 UI 동기화 방법으로서,
(a) 클라이언트가 사전에 unique trace_id를 생성하여 사용자 query 전송 요청에 포함시키는 단계;
(b) 클라이언트가 상기 query 전송과 동시에 또는 직후, `/trace/poll/{trace_id}` endpoint로 polling을 시작하는 단계;
(c) 서버가 query 수신 시 즉시 (비즈니스 로직 진입 전) ContextVar 또는 동등 메커니즘으로 trace_id 컨텍스트를 설정하고 stage event 저장소를 초기화하는 단계;
(d) 서버가 각 처리 stage(엔티티 추출, 검색, 그래프 traversal, 메모리 검증, LLM 생성 등) 진입 시 ContextVar로부터 trace_id를 획득하여 stage event를 저장소에 기록하는 단계;
(e) 클라이언트의 polling 응답이 서버 최종 응답 도착 전이라도 누적된 stage event를 반환하여 UI를 stage별로 동기화하는 단계
를 포함하는 것을 특징으로 하는, 실시간 UI 동기화 방법.

### 청구항 2 (시스템)

LLM 기반 채팅 시스템으로서,
- (1) trace_id 컨텍스트 변수 (ContextVar 등) 와 stage event 저장소,
- (2) 클라이언트로부터 사전 생성된 trace_id를 수신하여 컨텍스트 변수를 즉시 설정하는 entry point,
- (3) 다양한 모듈에서 stage event를 컨텍스트 trace_id로 기록하는 logger,
- (4) 클라이언트가 polling할 수 있는 `/trace/poll/{trace_id}` endpoint,
- (5) polling 응답으로 UI를 stage별로 동기화하는 클라이언트 코드
를 포함하는 것을 특징으로 하는, 실시간 stage event 동기화 시스템.

### 청구항 3 (종속 — 클라이언트 trace_id 생성)

청구항 1에 있어서, 상기 trace_id는 UUIDv4 또는 동등 무작위 식별자이며 클라이언트가 `crypto.randomUUID()` 류 API로 생성하는 것을 특징으로 하는 방법.

### 청구항 4 (종속 — Race-free 보장)

청구항 1에 있어서, 서버는 query 수신 후 비즈니스 로직 진입 전에 ContextVar 설정과 저장소 초기화를 완료하여, 클라이언트 polling 시점이 서버의 비즈니스 로직 시작보다 빠르더라도 폴링이 빈 결과 또는 404를 반환하지 않는 것을 특징으로 하는 방법.

### 청구항 5 (종속 — ContextVar 전파)

청구항 1에 있어서, ContextVar는 Python `contextvars.ContextVar` 또는 동등 cross-async-task 컨텍스트 메커니즘이며, async/await 호출 체인 전체에 자동 전파되어 모듈별로 명시적으로 trace_id를 전달할 필요가 없는 것을 특징으로 하는 방법.

### 청구항 6 (종속 — Stage 메트릭)

청구항 1에 있어서, 각 stage event는 stage name, timestamp, 그리고 stage별 메트릭(tokens 수, 검색 docs 수, 그래프 노드 수 등)을 payload로 포함하는 것을 특징으로 하는 방법.

### 청구항 7 (종속 — Polling Cursor)

청구항 1에 있어서, polling 응답은 next_since cursor를 포함하여 클라이언트가 다음 polling 시 since=cursor 로 요청해 동일 event를 중복 수신하지 않는 것을 특징으로 하는 방법.

### 청구항 8 (종속 — 응답 도착 시 polling 중단)

청구항 1에 있어서, 클라이언트는 서버 최종 응답 도착 시 polling interval을 즉시 종료하여 불필요한 polling 부담을 방지하는 것을 특징으로 하는 방법.

### 청구항 9 (종속 — 사후 디버깅)

청구항 2에 있어서, stage event 저장소는 응답 후에도 일정 시간(예: 60분) 보존되어 사후 디버깅 또는 audit 용도로 동일 trace_id 조회가 가능한 시스템.

### 청구항 10 (종속 — 인프라 가벼움)

청구항 1에 있어서, 본 시스템은 WebSocket, SSE, gRPC streaming 등을 사용하지 않고 일반 HTTP REST polling만으로 동작하는 것을 특징으로 하는 방법.

## 7. 도면 (작성 필요)

- **도면 1**: 기존 패턴 vs 본 발명 패턴 비교 — 서버 발급 trace_id 대비 클라이언트 사전 송신
- **도면 2**: Race-free 보장 timeline — POST `/chat` 수신 → ContextVar 설정 → polling 도착 (모두 안전)
- **도면 3**: ContextVar 전파 흐름 — entry point → entity_extractor → search → graph_engine → memory_loom → llm_client (모든 모듈에서 동일 trace_id)
- **도면 4**: 클라이언트 UI 동기화 시퀀스 — query 송신 + polling 시작 → stage event 수신별 UI update → 응답 도착 + polling 중단

## 8. 실시예 (Working Example)

### 8.1 서버 측 (Python)

```python
# core/observability.py (Phase 1 구현 완료 — PR #67/97/138 머지, 메인 ≈ 245줄)
import contextvars
from datetime import datetime
from typing import Dict, List

_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_STORE: Dict[str, List[dict]] = {}

def start_trace(trace_id: str):
    _TRACE_ID.set(trace_id)
    if trace_id not in _STORE:
        _STORE[trace_id] = []

def log_stage(stage: str, payload: dict = None):
    tid = _TRACE_ID.get()
    if not tid: return
    _STORE[tid].append({
        "stage": stage,
        "ts": datetime.now().isoformat(),
        "payload": payload or {},
    })

def get_events(trace_id: str, since: int = 0):
    return _STORE.get(trace_id, [])[since:]
```

```python
# server_llmwiki.py
@app.post("/chat")
async def chat(req: ChatRequest):
    start_trace(req.trace_id)                      # ① 즉시 컨텍스트 설정
    log_stage("received", {"text_len": len(req.text)})

    entities = extract_entities(req.text)          # 내부에서 log_stage("entity_extraction", ...)
    docs = hybrid_search(entities)                 # log_stage("hybrid_search", ...)
    graph_ctx = graph_engine.expand(entities)      # log_stage("graph_dfs", ...)
    memory_loom.validate(graph_ctx)                # log_stage("memory_loom", ...)
    answer = llm_generate(req.text, graph_ctx)     # log_stage("llm_generation", ...)

    log_stage("done")
    return {"answer": answer}

@app.get("/trace/poll/{trace_id}")
async def poll(trace_id: str, since: int = 0):
    events = get_events(trace_id, since)
    return {"events": events, "next_since": since + len(events)}
```

### 8.2 클라이언트 측 (JavaScript)

```javascript
// frontend/static/chat.js (구현 예정 — PR #97)
async function sendQuery(text) {
  const traceId = crypto.randomUUID();
  let since = 0;

  const pollHandle = setInterval(async () => {
    const r = await fetch(`/trace/poll/${traceId}?since=${since}`);
    const j = await r.json();
    j.events.forEach(ev => updateUIStage(ev.stage, ev.payload));
    since = j.next_since;
  }, 200);

  const res = await fetch("/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text, trace_id: traceId}),
  });

  clearInterval(pollHandle);
  showFinalAnswer((await res.json()).answer);
}
```

## 9. 산업상 이용 가능성

본 발명은 LLM 챗봇 UI, 다중 모듈 inference 파이프라인 (RAG, agent), 백오피스 batch 작업 진척 모니터링, 비동기 작업 progress 표시 등 다양한 응용에서 사용자 UX 개선에 산업상 이용 가능하다.

---

## 10. 출원 시 체크리스트

- [ ] 발명자/출원인 정보 기재
- [ ] 도면 1~4 작성 (`assets/patent/stage4b-figs/` 권장)
- [ ] §6 청구항 한국어 법률 용어 검수
- [ ] §8 실시예 코드는 PR #67/#97 머지 후 실제 코드로 보강
- [ ] 공지예외 적용 신청서 별도 첨부
- [ ] disclosure_log.txt 의 D 후보 commit hash 정확히 확인 후 기재
- [ ] 출원료 6만원 (개인 감면 시 1.8만원) 납부

---

**End of skeleton.**
