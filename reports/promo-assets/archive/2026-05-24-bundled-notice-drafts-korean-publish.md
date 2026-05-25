# Bundled informational notice DMs — 2026-05-24 Korean LinkedIn publish

> 한국어 LinkedIn publish 시점에 함께 발송할 묶음 informational notice
> draft 2건. **운영자가 직접 발송** (LinkedIn DM + GitHub issue comment).
>
> 옵션 (b) — Korean URL + V3' Protocol v1 spec-land notice를 한 번에 묶음
> (per [[next_session_direction_1_entry]] memory). Track 1 success pattern
> ("land first + no action needed DM") 유지. 동의 요청 아님.
>
> 이전 cycle DM (영문 publish 시점) draft는 같은 archive 디렉토리의
> `2026-05-24-dm-drafts-direction-plan.md` 참조.

---

## DM 1 — Robin issue #448 follow-up comment

**Channel**: GitHub issue comment on `Hashevolution/James-RAG-Evol#448`

**Why issue not LinkedIn**: data-bearing exchange는 그쪽 ball을 던진 channel. issue #448은 Robin이 시작했고 "Excited to see where you and Ali take this next" hand-off. 같은 channel에서 다음 일정 + Korean URL + spec land 함께 알림.

### Draft

```
Korean version of the announcement is up:
https://www.linkedin.com/posts/jiwon-seo-8b8649237_researchgemma4-26b-moe-cross-model-data-activity-7464152765888602113-q7KF/

One more — V3' Protocol v1 just landed on main as a standalone spec:
docs/research/v3prime-protocol-v1.md (PR #457).

Your sweep on the 26b mode-split is the first external adoption row
in §11. The spec freezes the JSON schema you've been pulling as the
analysis template (raw_response_text is REQUIRED in v1, sha256 prefix
stays additive, 12-month grace before any breaking v2). If you ever
want to link the spec from your repo README or cite it in a write-up,
the commit hash is in the file header.

No action needed on your side — just signaling that the framework you
helped validate is now citable.
```

**Tone notes**: Korean URL은 informational. spec land + adopter table §11 highlight + schema freeze 명시 (그녀의 분석 pipeline 보호 의무 재확인). "No action needed" 명시.

---

## DM 2 — Ali LinkedIn DM

**Channel**: LinkedIn DM (그동안의 working channel)

**Why LinkedIn not GitHub**: Ali와의 sustained working dialogue. data-bearing artifact만 link.

### Draft

```
Hi Ali, two quick updates — no action needed.

(1) Korean version of the Direction 4 announcement is up:
https://www.linkedin.com/posts/jiwon-seo-8b8649237_researchgemma4-26b-moe-cross-model-data-activity-7464152765888602113-q7KF/

Same data + same 3-axis framing as the English version, just expanded
for Korean sovereign-AI readership. Same back-links to PR / Robin's
repo / issue #448.

(2) V3' Protocol v1 just landed on main as a standalone spec
(docs/research/v3prime-protocol-v1.md, PR #457). 441 lines, frozen
JSON schema + 12-month grace policy + adopter table. Your "ceiling
vs path" framing is woven into §8 (Worked examples — axis 3
model-scale efficiency); Robin's 26b sweep is the first external
adopter row in §11.

When you bring up the Gemini backend mid-June and Track 3 swap
activates, the spec is the protocol surface for any swap_eval
measurements — same JSON schema, same fixture design, same statistical
floor. Anything you measure under it slots directly into the joint
piece without re-derivation.

Talk soon.
Jiwon
```

**Tone notes**: Track 1 success pattern DM 그대로. "no action needed" 명시. 2 substantive 정보 (Korean URL + spec land). Ali "ceiling vs path" framing이 spec §8에 woven됐다는 점 명시 (그의 contribution이 spec에 lock-in).

---

## Sending sequence

1. **Korean LinkedIn publish 직후 (KST)** — Robin issue #448 comment 먼저
2. **30분~1시간 이내** — Ali LinkedIn DM (Robin notice 발송 사실 별도 명시 불필요 — 양쪽 channel-separation)

### 운영자 액션 체크리스트

- [x] Korean LinkedIn publish 완료 (URL 확보, activity-7464152765888602113)
- [x] PR #453 description에 Korean URL back-link 추가 (이번 PR 자동 처리)
- [x] launch-tracker.md 4 rows 추가 (EN publish + spec land + KO publish + X thread draft)
- [x] X thread draft archive (`archive/2026-05-24-x-thread-direction4-korean.md`)
- [ ] **DM 1 (Robin) — issue #448 comment paste** (위 draft 그대로 또는 약간 수정)
- [ ] **DM 2 (Ali) — LinkedIn DM paste** (위 draft 그대로 또는 약간 수정)
- [ ] **X thread 7-tweet publish** (KST 19-22시 또는 07-09시 peak)
- [ ] X thread publish 후 launch-tracker.md X row를 🟡 → ✅ 갱신 (별 commit, ~3 lines)

각 DM 발송 후 24시간 안 응답 없어도 정상 — owner stance 유지, 응답 reminder 없음.

---

## 메모리 update (이번 cycle 후)

- [[next_session_direction_1_entry]]의 "결정 대기 항목 2개 (a)" 부분이 fulfillment 됨 → 다음 갱신 시 "✅ 한국어 publish + 묶음 발송 완료 (2026-05-24)"로 변경
- [[robin_26b_2x2_matrix_watch]]의 hand-off action item 4번 ("Ali로 hand-off — 3D parameter space")는 V3' spec §8에 woven으로 부분 fulfillment (Track 3 swap activation 시 자동)
- 본 archive 파일이 다음 promo cycle (joint paper draft 시점)에 reference

---

## What this draft is NOT

- Joint paper outline 작성 trigger 아님 — Robin endorsement는 받았으나, Ali Gemini backend mid-June + 3 stacks 완성 후 진행
- Direction 1+5 진입 시점 약속 아님 — 운영자 일정에 따름
- Robin/Ali에게 답변 reminder 발송 아님 — informational only
