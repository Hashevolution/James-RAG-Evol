# Session Handover — 2026-05-09 (License & DCO Infrastructure)

> Successor to `v0.2.0-platform-track.md` for the narrow scope of:
> **(1) license decision follow-up**, **(2) external-PR DCO verification**,
> **(3) v0.3 plugin API preparation**.
>
> Owner of this document: **operator** (license/CLA decisions are
> business-track, not engineering-track).
>
> Status: opened 2026-05-09. Branch: `claude/plugin-api-license-setup-Y3NPO`.

---

## 0. TL;DR (60-second read)

- License: **stay MIT** (Hashevolution, 2026). No change for v0.2 / v0.3.
- Contributor agreement: **DCO (Developer Certificate of Origin)** via
  `Signed-off-by:` git trailer, verified by GitHub Actions on every PR.
  No CLA bot, no signed agreement.
- Plugin API (v0.3): the four interface types in `ROADMAP.md` are now
  broken down into 7 sub-deliverables (D1–D7), each landable as its own
  PR. See §5.
- This session ships **infrastructure files only** — no plugin code yet:
  - This handover doc
  - `.github/workflows/dco.yml`
  - `CONTRIBUTING.md` DCO section
  - `ROADMAP.md` v0.3 sub-task breakdown
  - `docs/VERSIONING.md` skeleton (deferred to next session unless time
    remains)

---

## 1. Why we are doing this now

v0.2 closed engineering-complete on 2026-05-08 (5 of 6 axes done; Axis 6
gated on second-user adoption — recruitment, not code). The v0.3 cycle
opens with a different shape of risk than v0.2:

- v0.2 risk = **internal correctness**. Solved by bench + trace + policy.
- v0.3 risk = **external contract**. We are about to invite outside
  contributors to write *plugins* against an API we will commit to
  supporting for 12 months.

That invitation needs three things in place before the first external
plugin PR opens:

1. A license that is unambiguous about derivative work (**MIT — done**).
2. A way to confirm contributors actually have the right to license
   the code they submit (**DCO — this session**).
3. An API spec that is small enough to keep stable for 12 months
   (**v0.3 D1–D7 — next sessions**).

Skipping any of these three before merging external code creates legal
and architectural debt that compounds every subsequent PR.

---

## 2. License decision — recorded

### Decision

**Keep MIT.** The current `LICENSE` file (Copyright (c) 2026
Hashevolution) is unchanged.

### Rationale

| Option | Why considered | Why rejected |
|---|---|---|
| MIT (kept) | Simplest, broadest compatibility, current. Operator does not need patent grant for v0.3. | — |
| Apache-2.0 | Patent grant; NOTICE file; better for v1.0 SDK ecosystem. | Patent risk is low at single-maintainer scale; Apache adds NOTICE-management overhead with no current benefit. Revisit at v1.0 gate. |
| Dual (Apache core + commercial domain pack) | Future revenue path. | Premature: no domain pack exists; CLA would become mandatory; reverses the "no parallel domains" rule. |

### Re-evaluation triggers

Re-open this decision **only** if one of these happens:

- A contributor ships code that materially depends on a patented
  algorithm and the patent holder is not the contributor.
- The first external pilot customer's legal team requires Apache-2.0
  in writing.
- v1.0 gate work begins (production-grade mother) — at that point,
  Apache-2.0 vs MIT is reconsidered as part of SDK packaging.

Until one of those happens, MIT stays. Do not relitigate.

---

## 3. Contributor agreement — DCO (Signed-off-by)

### Decision

**Use the Developer Certificate of Origin (DCO)**, version 1.1, verified
by a GitHub Actions check on every pull request. No CLA bot, no signed
agreement, no contributor database.

### Rationale

| Option | Operator burden | Contributor burden | Legal coverage |
|---|---|---|---|
| **DCO** (chosen) | One workflow file; PRs without `Signed-off-by` fail CI | One git config command (one-time); add `-s` to commits | Sufficient for MIT |
| CLA bot (e.g. cla-assistant.io) | Bot config + database of signers + privacy implications | Click-to-sign per first PR | Stronger; needed for Apache + dual-license |
| Both | Highest | Highest | Overkill at solo-maintainer scale |

DCO matches the project's current scale (solo maintainer, MIT, no
ecosystem yet). It is also the path Linux kernel, Docker, GitLab,
and many large OSS projects use. Upgrading DCO → CLA later is a
straightforward additive change; downgrading CLA → DCO is awkward.

### What contributors will see

When a PR opens without `Signed-off-by:` in every commit, the
`DCO` check fails with a link to instructions. No human review
needed to enforce.

### What the operator does (one time)

See §7, item B1.

---

## 4. Files this session will create or modify

| File | Action | Why |
|---|---|---|
| `docs/handovers/session-2026-05-09-license-infrastructure.md` | **create** | This document |
| `.github/workflows/dco.yml` | **create** | Automated DCO verification |
| `CONTRIBUTING.md` | **modify** | Add DCO section (KO + EN), reference `-s` flag |
| `ROADMAP.md` | **modify** | Expand v0.3 plugin API into D1–D7 sub-tasks; add license-decision footnote |
| `docs/VERSIONING.md` | **create** (if time) | SemVer + 12-month deprecation policy skeleton (referenced by ROADMAP v0.3 already) |

Files explicitly **not** touched this session:

- `LICENSE` — unchanged (MIT stays)
- `core/plugins/` — does not exist yet; intentionally deferred to next
  session per scope decision
- `packs/general/` — same; deferred
- `docs/PLUGIN_AUTHORING.md` — same; deferred

---

## 5. v0.3 Plugin API — sequential breakdown

The `ROADMAP.md` v0.3 section currently lists 8 deliverables as a flat
list. They are not all the same size. Below is the dependency-ordered
breakdown that each becomes its own PR.

> ### Roadmap checklist (v0.3 plugin API)
>
> - [ ] **D1** — `docs/VERSIONING.md`: SemVer + 12-month deprecation
>       policy. *Blocks D2 (interfaces need a stability promise).*
> - [ ] **D2** — `core/plugins/base.py`: typed interfaces for
>       `OntologyPack`, `PromptPack`, `UIPanel`, `Scorer` (no
>       implementations, just `Protocol` / `ABC` definitions + docstring
>       contracts). *Blocks D3, D5.*
> - [ ] **D3** — `core/plugins/manifest.py`: pack manifest schema
>       (`pack.toml`: name, version, JAMES API range, hash, entry points).
>       *Blocks D4.*
> - [ ] **D4** — `core/plugins/loader.py`: `JAMES_PLUGINS=` env-driven
>       dynamic loader; SemVer enforcement against `JAMES_API_VERSION`;
>       refuses unsigned-manifest packs. *Blocks D5.*
> - [ ] **D5** — `packs/general/`: extract JAMES's current default
>       behavior as the dogfood pack (ontology, system prompts, etc.).
>       Removing it must break the server with a clear error;
>       `packs/general/` re-installed must produce byte-identical STEP 7
>       results vs v0.2 main.
> - [ ] **D6** — `JAMES_WORKSPACE=` env var: per-instance data root,
>       independent of pack selection. *Independent of D1–D5.*
> - [ ] **D7** — `docs/PLUGIN_AUTHORING.md`: end-to-end author guide
>       written so a new contributor can build a no-op pack in < 1 day.
>       *Depends on D1–D5 being shippable.*
>
> Ordering: **D1 → D2 → D3 → D4 → D5 → D7**, with D6 landing in any
> slot (it is orthogonal). Knowledge-cascade work
> (`docs/design/v0.3-knowledge-cascade.md`) is a separate v0.3 track,
> not gated on D1–D7.

Each PR must:

1. Include a `## Verification` section that passes `python scripts/bench.py
   --suite=step7 --check` (CLAUDE.md rule 2 — applies to anything under
   `core/` even when functionality is unchanged).
2. Include `## Out of scope` listing what is intentionally deferred.
3. Be signed off (`git commit -s`) per the DCO workflow added this
   session — including the maintainer's own commits.

### Estimated calendar

| PR | Estimated effort | Earliest | Latest |
|---|---|---|---|
| D1 | 2–3 hours | this week | +1 week |
| D2 | 1–2 days | next week | +2 weeks |
| D3 | 1 day | next week | +2 weeks |
| D4 | 2–3 days | +2 weeks | +4 weeks |
| D5 | 3–5 days (highest risk; touches existing behavior) | +4 weeks | +6 weeks |
| D6 | 1 day | any | +6 weeks |
| D7 | 2 days, AFTER D1–D5 | +6 weeks | +8 weeks |

These are aspirational; v0.2 axes typically slipped 30%.

---

## 6. Out of scope for this session (do NOT do)

- Do not write `core/plugins/*` even as a placeholder. Empty modules are
  worse than missing modules at this stage — the loader signature gets
  guessed and locks in.
- Do not change `LICENSE`. The decision is recorded in §2; revisit only
  on triggers in §2.
- Do not enable `Require signed commits` on GitHub branch protection
  (DCO ≠ GPG signing — see §7 B3 confusion warning).
- Do not add a CLA bot. The DCO decision in §3 supersedes any earlier
  draft suggestion to use cla-assistant.io.
- Do not add the DCO check to existing `main` branch protection without
  first letting one PR run end-to-end (otherwise the operator's own
  next merge will block).

---

## 7. Operator action checklist (manual, GitHub-side)

These steps **cannot** be done from a Claude Code session — they
require the operator's GitHub login. Do them in the order shown.
Each step is written for someone who has never configured GitHub
branch protection or signed a git commit before.

> ### Operator checklist
>
> - [ ] **B1** — Configure git locally to add `Signed-off-by` automatically
> - [ ] **B2** — Verify the DCO workflow runs green on a test PR
> - [ ] **B3** — Add the DCO check to `main` branch protection
> - [ ] **B4** — Pin DCO instructions to README (3-line addition)
> - [ ] **B5** — (Optional) Add a `dco-failure` issue template stub

---

### B1 — Configure git locally to add `Signed-off-by` automatically

**Goal**: every commit you make from now on automatically includes
`Signed-off-by: Your Name <you@example.com>` at the bottom.

**Do this once on your laptop** (not on the server):

1. Open a terminal.
2. Check what name and email git currently uses:
   ```
   git config --global user.name
   git config --global user.email
   ```
   If either prints nothing, set them now (use the same email as your
   GitHub account):
   ```
   git config --global user.name "Your Real Name"
   git config --global user.email "you@example.com"
   ```
3. From now on, when you commit, add the `-s` flag:
   ```
   git commit -s -m "fix: example"
   ```
   You will see at the bottom of the commit message:
   ```
   Signed-off-by: Your Real Name <you@example.com>
   ```
   That single line is the DCO sign-off. Nothing else is required.
4. (Optional) To make `-s` automatic without typing it, install a
   `prepare-commit-msg` hook. Skip this for now — `-s` is one
   character.

**What this does NOT mean**: it does **not** GPG-sign your commit.
GPG signing (the green "Verified" badge on GitHub) is a separate
thing and is **not required** by the DCO workflow. Do not enable
"Require signed commits" branch protection — that is a different
feature and will block your own merges.

---

### B2 — Verify the DCO workflow runs green on a test PR

**Goal**: prove the workflow added this session actually works before
relying on it for external PRs.

1. After this session pushes the `claude/plugin-api-license-setup-Y3NPO`
   branch, open it in your browser:
   `https://github.com/hashevolution/james-rag-evol/pull/new/claude/plugin-api-license-setup-Y3NPO`
2. Open a draft PR against `main`. (Draft = not ready to merge yet.)
3. Look at the **Checks** tab on the PR. You should see a check named
   `DCO`. It should be **green** (because every commit on this branch
   was made with `-s` per the DCO workflow we are about to enable).
4. If `DCO` is **red**:
   - Click "Details" → it will tell you which commit lacks
     `Signed-off-by`.
   - On your laptop, fix it with:
     ```
     git rebase --signoff main
     git push --force-with-lease
     ```
     (`--force-with-lease` is safer than `--force`; if someone else
     pushed to your branch in the meantime, it refuses rather than
     overwriting their work.)
5. Once `DCO` is green, **do not merge yet**. Continue to B3.

---

### B3 — Add the DCO check to `main` branch protection

**Goal**: from now on, no PR can merge into `main` without a green
`DCO` check.

1. Go to:
   `https://github.com/hashevolution/james-rag-evol/settings/branches`
2. Find the rule for `main`. (If none exists yet, click
   "Add branch protection rule", branch name pattern: `main`.)
3. Scroll to **"Require status checks to pass before merging"**.
   - Tick the box if not already ticked.
   - In the search field below, type `DCO` and select the check that
     appears. (It only appears in this list **after** the workflow has
     run at least once — that is why B2 had to happen first.)
   - Tick **"Require branches to be up to date before merging"**.
4. Scroll further. Confirm these are **NOT** ticked:
   - "Require signed commits" (this means GPG, not DCO; leave OFF)
   - "Require linear history" (optional; orthogonal to DCO)
5. Click **Save changes**.
6. Now merge the test PR from B2. It should merge green.

---

### B4 — Pin DCO instructions to README (3-line addition)

**Goal**: external contributors should not have to read CONTRIBUTING.md
in full just to find out their PR was rejected for missing `-s`.

The Claude session will add the long-form DCO section to
`CONTRIBUTING.md`. You add a 3-line pointer to `README.md`:

1. Open `README.md` in any editor.
2. Find the "Contributing" section (it likely already exists). If not,
   add one near the bottom.
3. Add this paragraph:

   ```markdown
   ### Sign-off required

   All commits to this repo must include a `Signed-off-by:` line per
   the [Developer Certificate of Origin](https://developercertificate.org).
   The simplest way: use `git commit -s` instead of `git commit -m`.
   See [CONTRIBUTING.md → DCO](CONTRIBUTING.md#dco-signed-off-by) for
   the full explanation.
   ```

4. Repeat for `README.ko.md` (Korean version) — same content, translated:

   ```markdown
   ### 사인오프 (Sign-off) 필수

   이 저장소의 모든 커밋은 [DCO (Developer Certificate of
   Origin)](https://developercertificate.org)에 따라 `Signed-off-by:`
   라인을 포함해야 합니다. 가장 간단한 방법: `git commit -m` 대신
   `git commit -s`를 사용하세요. 자세한 설명은
   [CONTRIBUTING.md → DCO](CONTRIBUTING.md#dco-signed-off-by) 참조.
   ```

5. Commit (with `-s`!) and push.

---

### B5 — (Optional) `dco-failure` issue template stub

**Goal**: the most common contributor confusion ("my PR went red, what
do I do?") gets a one-click answer.

Skip this if you have not seen the confusion yet. Add it the first time
an external contributor asks.

1. Create the file `.github/ISSUE_TEMPLATE/dco-help.md` with this
   content:

   ```markdown
   ---
   name: DCO check failed on my PR
   about: Your pull request shows a red "DCO" check
   title: "DCO check failed: <your PR number>"
   labels: dco
   ---

   The DCO check fails when one or more of your commits is missing a
   `Signed-off-by:` line. To fix:

   1. On your branch, run:
      ```
      git rebase --signoff main
      git push --force-with-lease
      ```
   2. Reload your PR. The DCO check should re-run and turn green.

   If that does not work, paste the error message from the failed
   check below and we will help.
   ```

2. Commit and push.

---

## 8. What the next Claude Code session should do

In order, after this session lands and operator B1–B3 are done:

1. Open `docs/VERSIONING.md` (skeleton in this branch if time allowed,
   else create from scratch). Fill in: SemVer table, 12-month
   deprecation policy, plugin API version vs JAMES version mapping.
   This is **D1** in §5.
2. Move to **D2** (`core/plugins/base.py`). Open a separate branch
   (`feat/v0.3-plugin-base`). Bench numbers required because the file
   sits under `core/`.
3. Continue D2 → D3 → D4 → D5, each as its own PR. D6 can land any
   time. D7 last.

Do not start D2 until the operator has confirmed B1–B3 are done. The
maintainer's own commits to `core/plugins/` will be DCO-checked by the
workflow added this session, and the first failure mid-stream is more
disruptive than a one-day delay up front.

---

## 9. Companion documents

| Document | Purpose |
|---|---|
| `CLAUDE.md` | Session-start primer — read first |
| `docs/PLATFORM_READINESS.md` | 6-dimension readiness + v0.3 / v0.4 / v1.0 gates |
| `docs/handovers/v0.2.0-platform-track.md` | v0.2 engineering handover (still authoritative for non-license work) |
| `docs/handovers/v0.2.1-business-track.md` | "no parallel domains" rule + business frame |
| `ROADMAP.md` | Includes the D1–D7 expansion added this session |
| `CONTRIBUTING.md` | Includes the DCO section added this session |
| `.github/workflows/dco.yml` | The actual DCO check |
| `docs/VERSIONING.md` | (D1) — created in this branch if time, else next session |

---

## 10. 한국어 요약

이 세션에서 다음을 결정·기록·구축합니다:

1. **라이선스: MIT 유지.** Apache-2.0 전환은 v1.0 게이트나 외부 파일럿 고객 법무팀
   요구가 있을 때만 재검토. §2의 트리거 외에 재논의 금지.
2. **기여자 검증: DCO (Signed-off-by).** CLA 봇·서명 동의서 사용 안 함.
   GitHub Actions가 PR마다 자동 검증. 솔로 메인테이너 + MIT 조합에 적합.
3. **v0.3 플러그인 API 세분화: D1~D7.** ROADMAP.md의 평면 리스트를 의존
   순서가 명확한 7개 PR로 분해 (§5). 각 PR은 STEP 7 bench + DCO 사인오프 필수.
4. **이번 세션 산출물:** 핸드오버 (이 문서) + `.github/workflows/dco.yml` +
   `CONTRIBUTING.md` DCO 섹션 + `ROADMAP.md` v0.3 세분화. 코드는 손대지 않음.
5. **운영자가 직접 해야 할 일 (§7):** B1 git 사인오프 설정 → B2 테스트 PR로
   워크플로우 검증 → B3 main 브랜치 보호 규칙에 DCO 체크 추가 → B4 README에
   3줄 안내 추가 → (선택) B5 이슈 템플릿. **반드시 B1 → B2 → B3 순서.**

다음 세션 진입 전 운영자 B1~B3 완료 필수. 그 다음 D1 (`docs/VERSIONING.md`)
부터 시작.
