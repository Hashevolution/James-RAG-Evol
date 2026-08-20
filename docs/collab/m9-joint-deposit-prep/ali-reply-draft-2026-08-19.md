# Ali Afana 답장 초안 — 2026-08-19 (최소판)

**상태**: **SENT 2026-08-19.** (발송 완료 — 이후 Ali 최종본 회신 → 2차 답장 `ali-reply-2-draft-2026-08-19.md`)
**채널**: Ali가 보낸 이메일에 회신. LinkedIn 중복 발송 불필요(본인이 "동일 메시지"라 명시).
**설계 원칙**: Ali가 실제로 답을 기다리는 항목 = 그의 편지 말미
`WHAT I NEED BACK, FROM EACH OF YOU` 4개. 이 답신은 그 4개 + 비용 0인
메타데이터 사실 정정 2건만 담는다. **이행 의무가 생기는 내용은 넣지 않는다.**

## 발송 전 조건 — 1건

**정정 커밋을 `main`에 병합할 것.** 편지 2문단이 "Fixed on my side"라고
말하는데, 정정은 현재 `claude/two-context-mode-split-review-fhckhf`
브랜치에만 있다. `origin/main`에는 유령 행
(`docs/release_notes_v0.4.0.md:93` = `v0.4.0-alpha.1 —
10.5281/zenodo.20374227`)과 낡은 `PR #440` 표기가 그대로 살아 있어서,
Ali가 저장소를 열면 정정이 보이지 않는다. **병합 후 발송.**

### 확인 불필요 (이미 종결된 항목 — 재확인 요구하지 말 것)

- **v0.3.3 = `10.5281/zenodo.20374227`** — 확정. PR #520이 이 번호를
  alpha.3의 `isNewVersionOf`로 추가했고, alpha.3 notes가 그 대상을
  *"chain back to v0.3.3 (10.5281/zenodo.20XXXXXX, operator-supplied at
  publish time)"* 로 명시한다. `v0.4.0-alpha.1`은 존재한 적이 없다
  (alpha.2가 스스로를 "the first alpha tag"라 선언, PR·태그·릴리스·CHANGELOG
  전부 부재). Zenodo Versions 탭을 열어도 추가 정보가 나오지 않는다.
- **concept DOI** — 발송 선행조건이 아니다. 편지의 답이 "확인해 줄 수 없고,
  어차피 최신 버전(v0.4.4)으로 리졸브되므로 v0.3.x 인용에 쓰면 안 된다"이므로
  번호를 알아내야 답할 수 있는 구조가 아니다. 저장소에 concept DOI를 기록해
  두는 것은 별건의 위생 작업.

## 이번 답신에서 의도적으로 뺀 것 → 자체 수행 후 추가 답신

Ali가 요구한 항목이 아니고("cheap for you to check"이라고만 했음), 답하는 순간
이행 의무가 생긴다. **먼저 우리가 수행하고, 결과가 나온 뒤 2차 답신으로 묶어 보낸다.**
이번 편지의 마지막 문단이 그 자리를 열어두는 역할만 한다(기한·범위 약속 없음).

| 보류 항목 | 자체 수행 계획 | 2차 답신에 담을 것 |
|---|---|---|
| ① bidi — control-char strip → span 제거 | `core/input_normalization.py` 재설계 + 회귀 테스트. fixture 미정규화 경계 유지 | 수정 사실 + 그의 정정이 맞았다는 확인 |
| ② `\d` ASCII-only | Python 스코어러는 재현 안 됨(유니코드 `\d`). 대신 `frontend/static/chat.js` 인용/제안 파싱(JS `\d` = ASCII)이 동일 클래스 → 수정 | "우리 쪽에선 가격 추출이 아니라 렌더러에서 났다" |
| ③ 아랍어 keyword gate | 런타임 게이트 NFC→NFKC + tatweel/alef-maqsura folding, 스코어러 substring 기준 동일 적용 | 적용 범위 |
| ④ run identity salting | `adversarial_sweep` 케이스별 salted `session_id` → Track 2c 18-case 재측정 | **수정된 cross-stack 비교표** + bidi_02 각주 정정 여부. 단 V3'/D1 드라이버는 Ollama 직결이라 joint record 숫자는 무관하다는 범위 한정 |
| ⑤ 그의 replay 드라이버 실행 | 로컬 Ollama로 실행 | 재현/미재현 결과 |
| ⑥ Vadym 4번째 저자 | Robin Phase 1(자연 트리거 piggyback) 선행. 단독 DM 금지 | Phase 1 완료 후 Ali에게 통지 |
| ⑦ 헤드라인 보존 / Robin DOI 추가 제안 | 없음(비용 0) | 2차 답신에 한 줄씩 |

**주의**: ④는 우리 published 비교 문서의 수정 가능성을 품고 있으므로, 재측정 전에는
어떤 형태로도 Ali에게 수치를 재확인해 주지 않는다.

---

Ali,

Two months is your call to make, not a debt — you said what the reason
was, and that is enough said about it. You asked to be read as a
submission before being asked for a signature, so I read it that way
first. The record holds together and it reconciles with its own README:
four caps x N=20 x two call shapes gives the 160, the 80 routing calls
at one distinct output and 49 completion tokens flat, and the synthesis
medians moving 130.5 -> 118.5 across a 10x cap range are the same 12
tokens your letter quotes. The scope section does the work you built it
to do — declaring that the deployed app runs at default temperature
while the sweep pinned T=0.2, and that what should survive temperature
is the token count rather than byte equality, is the kind of admission
a reviewer would otherwise have to extract. I would not soften any of
it.

The one thing to change is my axis, and the error is mine rather than
yours. The bullet cites the seven-tier gradient as "PR #440, Issue
#448". PR #440 is V3'.e, merged 2026-05-23, and it measures *three*
workload levels (heavy 0/10, light 14/20, none 20/20 at cap=400) — the
word "seven-tier" does not appear in it, and it predates Direction 1.
The seven-tier result is **PR #461 + #463**, merged 2026-05-24 and
archived as v0.3.1 under 10.5281/zenodo.20363998, whose own Zenodo
`related_identifiers` cite #461, #463 and #457 and never #440. Issue
#448 is Robin's 26b data — cited under my bullet it reads as her leg
supporting mine, which is the collapse the three-axis split exists to
prevent. The cause: my joint-deposit prep folder labelled this axis
"workload gradient ... (PR #440)", correct while that axis *was* the
three-level split, and I never updated the pointer after v0.3.1
upgraded it to seven tiers. You took "seven-tier" from the DOI
description, which was right, and "#440" from my folder, which was
stale. Fixed on my side. In my words, for verbatim use:

> **Workload gradient (Seo):** inside retrieval middleware on
> gemma4:e4b, completion length at natural stop rises monotonically
> across a seven-tier task ladder — 62 -> 1681 tokens, 27x dynamic
> range, per-tier cross-sweep variation within 3-5% (V3-prime
> **Direction 1 closure, PRs #461/#463**, archived as
> 10.5281/zenodo.20363998; the earlier two-mode / three-workload split
> is **PR #440**, and Converse's cross-stack numbers are **Issue
> #448**). The measured quantity is total completion tokens
> (`eval_count`), which on this model includes a hidden reasoning
> trace: a follow-up decomposition found 5 of the 7 tiers are 82-98%
> trace, so the gradient's magnitude is part task workload and part
> reasoning-mode cost. The substitution baseline (2% trace) and the
> `reflect` tier (61%, 580 visible tokens) are the tiers carrying
> unambiguous workload signal.

One more factual item while the metadata is open. The forward-pointer
your record resolves — the notes on v0.3.1 and v0.3.3 — describes your
leg as "Provia, mid-June managed-Gemini cross-stack", and you delivered
a hosted gpt-4o-mini production router. Those records are minted and
not editable, so the joint deposit should say in one sentence that the
third leg was measured on a different backend than the one anticipated,
rather than leave a pointer resolving to a stack nobody used.

Your four questions. **Alphabetical authorship as drafted — yes**, no
reservation. **Publication -> report, CC-BY-4.0 — yes**; my own draft
already defaulted to CC-BY-4.0 for the joint record with the solo
records staying MIT, so we converged independently, and "report" keeps
the path to arXiv clean. **DOIs — cite all three individually and do
not use a concept DOI**: v0.3.1 `10.5281/zenodo.20363998`, v0.3.2
`10.5281/zenodo.20372649`, v0.3.3 `10.5281/zenodo.20374227`. I cannot
confirm `20363997` — I have never recorded a concept DOI, which is a
hygiene failure on my side — and in any case a Zenodo concept DOI
resolves to the *latest* version of the chain, which today is v0.4.4
(`10.5281/zenodo.20652679`); as a fallback for a v0.3.x citation it
would silently point at the wrong artifact.

Last, the one reviewer's objection I would raise, and it does not block
the deposit. Your conclusion is that the shipped prompt's "2-4
sentences" instruction rather than the cap is the binding constraint. I
believe the observation, but as measured two causes are confounded: the
prompt is length-instructed *and* gpt-4o-mini emits no reasoning trace.
On my side those are separable, which is why the caveat above exists —
verify is 1164 completion tokens against 23 visible ones, and disabling
reasoning reclaims 83-98% on five of seven tiers with the visible answer
unchanged. A model with no such trace is already floored near its
visible-answer length before any instruction applies. Separating them
costs one added cell — length instruction on/off x reasoning mode on/off
— and either outcome strengthens the record; I would write "the
instruction, not the cap, *appears* to be binding" and name the missing
cell rather than drop the finding. Separately, your four engineering
findings are being worked through here rather than taken on faith; I
will come back with what each one did or did not reproduce, in its own
message, once there is something measured to report.

— Jiwon Seo
Hashevolution / PROJECT JAMES
github.com/Hashevolution/James-RAG-Evol
ORCID 0009-0002-0007-7860
