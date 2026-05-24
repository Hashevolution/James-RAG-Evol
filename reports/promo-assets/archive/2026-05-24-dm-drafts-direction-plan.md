# Informational notice DM drafts — PR #449 land 후 발송

> 2026-05-23 PR #449 (6-direction measurement framework plan + 2026-05-23 Ali/Robin comments + 26b cross-stack data) land 후 발송할 informational DM 2건. **Track 1 success pattern** (land first + "no action needed" DM) 유지. 동의 요청 아님 — 결과 공유 + 다음 일정 명시.
>
> 사용자(Hashevolution)가 직접 발송 (LinkedIn DM + GitHub issue comment). 이 문서는 draft + 사용 가이드.

---

## DM 1 — Robin Converse (issue #448 comment)

**Channel**: GitHub issue comment on `Hashevolution/James-RAG-Evol#448`

**Why issue comment, not LinkedIn**: data-bearing exchange는 그쪽 ball을 던진 channel에서 응답. issue #448은 그녀가 시작했고 "Excited to see where you and Ali take this next"로 명시 hand-off. 같은 channel에서 first acknowledgment + 다음 일정. LinkedIn은 추후 결과 announce 시.

### Draft

```
Robin — data received, thanks for the protocol-exact mirror.

Three things land on our side from this:

1. The bit-for-bit determinism (40/40 unique=1, eval_count=38 flat on 26b) sharpens the mode-split mechanism in a way our V3'.e didn't measure yet. We're patching the V3'.e driver to record unique-output count per cell + re-running on e4b within the week. If e4b shows the same bypass-sampling signature, axis 1 ("substitution mode bypasses temperature sampling") graduates to a publishable mechanism on its own.

2. Both reference signatures shifting (62→38 / 400-450→49-54) hit our pre-registered "next research thread" arm — but the systematic direction (26b uniformly more token-efficient) reveals what you correctly called a third axis: model-scale efficiency. The 3-axis framing (your mode split + JAMES workload gradient + your model-scale efficiency) is now locked on our side. Joint paper outline updated to three-author role-split with that structure.

3. The 6-direction follow-up plan landed on main today as PR #449 — handover at `docs/handovers/v0.3.x-measurement-framework-track.md`. Direction 4 (e4b unique-count verification, mirroring your Finding 1) is this week; Direction 3 (cross-family generalization on Llama / Qwen / DeepSeek) lands in month 2 and you see results first since it judges axis 1 universality.

JSON schema stays frozen until your downstream analysis is settled. Any additions will be backward-compatible additive fields only.

Talk soon —
Jiwon
```

**Tone notes**: substantive (data-bearing acknowledgment), specific (3 concrete points, all actionable), no over-thanks, no consent-seeking. "We're patching" / "lands in month 2" / "you see results first" = owner stance preserved + courtesy maintained. JSON schema freeze 명시는 그녀의 분석 pipeline 보호 의무 ack.

---

## DM 2 — Ali Afana (LinkedIn DM)

**Channel**: LinkedIn DM (그동안의 working channel)

**Why LinkedIn, not GitHub**: Ali와의 sustained working dialogue는 LinkedIn DM. data-bearing artifact(PR URL)만 link로. 그쪽 inbox에 짧게.

### Draft

```
Hi Ali,

Quick update — no action needed on your side.

PR #449 landed on main today (URL: https://github.com/Hashevolution/James-RAG-Evol/pull/449). Three things in it that affect the joint-piece narrative we agreed on:

(a) Your 10-word framing ("Substitution is free. Synthesis costs in proportion to what it has to invent.") is now the three-author locked headline — Robin endorsed it explicitly in her sub-reply yesterday, and the cost-asymmetry framing has both your name and hers attached.

(b) Robin shipped the 26b 2×2 matrix the same day she committed to it (issue #448 on our repo + companion repo triavalabs/gemma4-26b-mode-split). Both reference signatures shifted vs e4b — 26b synthesis is ~9× more token-efficient, with 100% success vs 70%. New third axis: model-scale efficiency. Three-author role-split on the joint paper: your deployment-context divergence, her mode split + model-scale efficiency, our workload gradient.

(c) Six follow-up directions queued for v0.3.x — handover at `docs/handovers/v0.3.x-measurement-framework-track.md`. Direction 5 (auto-routing layer on top of the Provider Contract you'll implement against) is in scope for month 2. I'll send you the design preview before the implementation lands, so you can flag anything that would change the contract surface. The contract surface itself stays unchanged — router is one layer above.

Your mid-June Gemini backend timeline + ar_ecommerce.yaml 6/1 calendar both unchanged on our side. Talk soon.

Jiwon
```

**Tone notes**: Track 1 success-pattern DM 그대로. "no action needed" 명시. 3개 substantive 정보 (Ali framing endorse / Robin 26b data / Direction 5 preview-coming). 그의 mid-June 일정 + ar_ecommerce 일정 zero 영향 명시.

---

## Sending sequence

1. **PR #449 머지 직후** (CI 통과 + self-merge): Robin DM 1 먼저 (그쪽이 ball 던졌으므로 응답이 우선)
2. **그 후 30분~1시간 이내**: Ali DM 2 (Robin DM 발송 사실은 DM 2에 명시되어 있음)

### 사용자(Hashevolution) 액션 체크리스트

- [ ] PR #449 CI 완료 확인 (`gh pr checks 449`)
- [ ] PR #449 self-merge
- [ ] DM 1 (Robin) — issue #448에 comment 형식으로 paste (위 draft 그대로 또는 약간 수정)
- [ ] DM 2 (Ali) — LinkedIn DM으로 paste
- [ ] launch-tracker.md에 발송 사실 row 2건 추가 (informational notice 발송 timestamp + 응답 wait)

각 DM 발송 후 24시간 안 응답 없어도 정상 — owner stance 유지, 응답 reminder 없음.

---

## What this draft is NOT

- 동의 요청 아님 — Direction 4-6 모두 단독 진행, DM은 후속 informational
- 협업 재협상 아님 — Track 3/4/5 calendar 변경 zero
- 발견 자랑 아님 — 3-author lock된 결과를 그들의 contribution과 함께 정리

## 한국어 부연 (초등학생 비유)

- "친구한테 '내가 너랑 한 약속 정리해서 이만큼 진행했어, 너 일정엔 영향 없어' 알려주는 짧은 카톡"
- 동의 받으려는 거 아님 (그건 약자 위치). 진행 사실 알리는 거 (그게 owner 위치).
- 답장 오면 좋고, 안 와도 우리 일은 계속 진행됨.
