# PROJECT JAMES — Governance

> **Status**: v0.3.x (Platform Skeleton phase)
> **Adopted**: 2026-05-20
> **Companion documents**:
> - [`CLAUDE.md`](CLAUDE.md) — session-level operating rules (always-on)
> - [`CONTRIBUTING.md`](CONTRIBUTING.md) — contributor workflow + CLA
> - [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — community standards
> - [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — design principles + non-goals
> - [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md) — 6-dimension gates
> - [`docs/LICENSE_PLAN.md`](docs/LICENSE_PLAN.md) — license-evolution triggers

This document describes how decisions get made on PROJECT JAMES. It is
deliberately short: the project is in alpha (v0.3.x), the maintainer count
is one, and the rules below favor clarity over ceremony. Governance scales
with the project; this document will be revisited at each gate
(v0.4, v1.0).

---

## 1. Project model

PROJECT JAMES is a **single-maintainer (BDFL) project through v1.0**.

- **BDFL**: Jiwon Seo (`@Hashevolution` on GitHub), referred to in this
  document as "the maintainer".
- All design, release, and license decisions terminate at the maintainer.
- The maintainer is expected to publish the *reasoning* behind decisions
  in writing (PR description, CHANGELOG entry, or handover doc under
  `docs/handovers/`) so contributors can model the project's direction
  without asking.

After v1.0 the project will transition to a **multi-maintainer model with
domain pack ownership**. The transition plan is tracked under
`docs/PLATFORM_READINESS.md` and will land as a governance amendment PR
before the v1.0 gate.

### Why BDFL through v1.0

The mother-platform thesis (CLAUDE.md §1, ARCHITECTURE.md) requires that
the platform contract — what `core/` exports, what plugins may assume,
what trust zones exist — stay coherent. With one decision-maker, the
contract drifts less. Community-style governance with rotating reviewers
will arrive when there is a contract worth protecting (v1.0), not before.

---

## 2. Roles

| Role | Who | Responsibilities | Permissions |
|---|---|---|---|
| **Maintainer** | Jiwon Seo (`@Hashevolution`) | Reviews and merges PRs · sets roadmap · cuts releases · owns license decisions · enforces CoC | Force-push to `main` (avoided in practice) · approve security disclosures · sign releases |
| **Reviewer** | Maintainer (sole reviewer at v0.3.x) | Reviews PRs against bench, security, scope, and CLAUDE.md rules | Approve / request-changes on any PR |
| **Contributor** | Anyone with a signed CLA | Opens PRs, files issues, posts in Discussions, signs CLA on first PR | Open PRs · comment · file issues |
| **Reporter (security)** | Anyone | Files a security advisory via the process in [`SECURITY.md`](SECURITY.md) | Receives credited disclosure (if requested) on fix release |
| **Reporter (CoC)** | Anyone | Files a CoC report to `karu-7@hanmail.net` | Reports handled confidentially per [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) |

There are currently **no formal sub-maintainers, area owners, or release
managers** — those roles are anticipated for the post-v1.0 transition.

### Becoming a contributor

1. Read [`CLAUDE.md`](CLAUDE.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).
2. Open a PR. The CLA Assistant bot will request a one-click signature on
   first contribution (see [`docs/legal/CLA.md`](docs/legal/CLA.md); for
   non-CLA paths, see [`docs/legal/non-cla-contributions.md`](docs/legal/non-cla-contributions.md)).
3. The maintainer reviews; substantive contributors may be invited to
   reviewer rotation post-v1.0.

---

## 3. Decision-making

Decisions fall into three classes, each with a defined process.

### Class A — Code change (default path)

1. Contributor opens a PR.
2. Maintainer reviews against:
   - CLAUDE.md operating rules (no domain features pre-v1.0, no
     trust-boundary bypass, no module > 20 KB)
   - Bench numbers for PRs touching `core/retrieval`, `core/graph`, or
     `core/reasoning` (CLAUDE.md rule 2)
   - Test coverage for new behavior
   - Security implications (per `SECURITY.md`)
3. Maintainer merges (squash by default) once gates pass. PRs are not
   auto-merged on trust-boundary touches (auth, policy, sandbox).

### Class B — Architecture / non-goal change

A change that adds a new module trust zone, removes a non-goal listed in
`docs/ARCHITECTURE.md`, or alters the plugin contract requires:

1. A PR to `docs/ARCHITECTURE.md` with the `architecture` label.
2. A 72-hour public-comment window (Discussions or the PR itself).
3. Maintainer merge with a recorded rationale in the PR body and a
   CHANGELOG entry.

### Class C — License or governance change

A change to `LICENSE`, `docs/LICENSE_PLAN.md`, `GOVERNANCE.md`, the CLA,
or the CoC requires:

1. A PR with the `governance` label.
2. A 7-day public-comment window in Discussions, linked from the PR.
3. Notification to past contributors (where the CLA relicensing grant
   applies) via the project's GitHub Discussions.
4. Maintainer merge with the rationale recorded in the PR body.

The CLA's §4-bis Relicensing Grant exists specifically to make Class C
changes tractable; see [`docs/legal/CLA.md`](docs/legal/CLA.md) for
boundaries.

---

## 4. Release process

PROJECT JAMES uses **semantic-versioned alpha releases** during v0.x.

| Step | Owner | Artifact |
|---|---|---|
| Cut a release branch / tag candidate | Maintainer | `vX.Y.Z` tag on `main` |
| Update `CHANGELOG.md` with the entry | Maintainer | A new section under `## [vX.Y.Z]` |
| Verify bench gates (STEP 7 baseline + diagnostic + security suites) | Maintainer | `[bench] OK` line in release notes |
| Cut GitHub Release | Maintainer | Release notes link to `docs/release_notes_vX.Y.Z.md` |
| Update `README.md` status badge if the cycle theme changed | Maintainer | Badge + status section |
| Archive the cycle launch tracker (if a promo cycle is closing) | Maintainer | `reports/promo-assets/archive/vX.Y.Z-launch-tracker.md` |

Releases are cut from `main` only. There are no separate release branches
during v0.x. Pre-releases (e.g., `v0.4.0-rc1`) may be tagged for community
verification at the maintainer's discretion.

---

## 5. Operating rules (inheritance from CLAUDE.md)

The following rules are **load-bearing for governance** and are enforced
at PR-review time. They live in `CLAUDE.md` so every Claude Code session
sees them; they are summarized here so external contributors find them
without reading the session brief.

1. **No new domain features** (legal, food, retail, travel, finance,
   government, etc.) until v1.0. Mother-hardening only.
2. **Bench numbers required** for PRs touching `core/retrieval`,
   `core/graph`, `core/reasoning`. No numbers → no merge.
3. **Self-evolution is opt-in only.** Any change that allows auto-deploy
   without an `approver_username` in the audit log is a bug.
4. **Architecture changes** (new module, new trust zone, removal of a
   non-goal) require an `architecture`-labeled PR to
   `docs/ARCHITECTURE.md`.
5. **Module size gate**: no file in `core/` exceeds 20 KB. Split first.
6. **No PolicyEngine bypass** for "quick fixes". Trust boundaries are
   the contract.

A PR that violates any of these will be marked `changes-requested` with
a link to the relevant rule.

---

## 6. Conflict resolution

The project is small enough that disputes are resolved by direct
conversation, but the path of escalation is documented for predictability:

1. **PR-level disagreement** — discuss in the PR. If unresolved in 72
   hours, open a Discussion linked from the PR.
2. **Direction-level disagreement** (the maintainer says "out of scope",
   the contributor says "this is exactly what the platform needs") —
   open a Discussion. The maintainer will publish a written rationale
   within 7 days. The decision is final at v0.3.x; this is the BDFL
   model, not consensus.
3. **CoC violation** — follow the process in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
   Reports go to `karu-7@hanmail.net`, not to public channels.
4. **Security disagreement** — follow the process in [`SECURITY.md`](SECURITY.md).

If a contributor disagrees with a maintainer decision at a level that
cannot be reconciled, **forking is explicitly supported under the MIT
license**, and the maintainer will not retaliate against forks. The
project's non-CLA contribution path (`docs/legal/non-cla-contributions.md`)
exists in part to make this exit reversible.

---

## 7. Access continuity

> **OpenSSF criterion `access_continuity`** (MUST): The project MUST be
> able to continue with minimal interruption if any one person dies, is
> incapacitated, or is otherwise unable or unwilling to continue
> support of the project — within a week of confirmation.
>
> **Current status (2026-05-20): UNMET — mechanism documented, lockbox
> deposit pending.** This section describes the intended mechanism and
> the timeline to make it operational. Once the milestones in §7.4 are
> complete the status flips to MET and the badge submission can claim
> the criterion. Until then this section is itself the audit trail.

### 7.1 Why this matters now

The project is single-maintainer (§1). If Jiwon Seo (`@Hashevolution`)
is incapacitated or unreachable, the following operations would block
**without a continuity mechanism**:

- Closing or commenting on issues (requires repo write)
- Merging community PRs (requires repo write + branch-protection
  override authority)
- Cutting a release tag (requires repo write + maintainer signing key)
- Renewing project domains (if/when registered) and any PyPI / npm /
  Docker Hub credentials (if/when published)
- Rotating the GitHub `CLA_BOT_PAT` secret used by
  `.github/workflows/cla.yml`
- Responding to security advisories (admin permission required to view
  draft advisories)

A bus factor of 1 (§8) makes this a structural risk, not a hypothetical.

### 7.2 The mechanism (target state)

Following the OpenSSF-suggested **lockbox + legal heir** model:

| Asset | Recovery path | Verifier |
|---|---|---|
| GitHub repo admin access | Encrypted recovery kit (password manager emergency export) sealed in a physical safe-deposit box or equivalent secure storage. | A designated legal heir holds the box key / access credentials. |
| GitHub `CLA_BOT_PAT` and CI secrets | Same lockbox. | Rotation procedure documented in `.github/workflows/cla.yml` header. |
| Project domain credentials (if/when registered) | Domain registrar account credentials in lockbox. | DNS heir designated in the will (legal rights to transfer). |
| Package-registry accounts (PyPI / npm / Docker Hub, if/when published) | Account credentials in lockbox. | Same heir. |
| Maintainer's PGP / signing key | Encrypted secret in lockbox; passphrase split between the heir and the maintainer's legal representative via Shamir's Secret Sharing (2-of-3) or equivalent. | Heir + legal representative. |
| Email contact `karu-7@hanmail.net` (CoC reports, security contact backup) | Email account credentials in lockbox. | Heir. |

The **lockbox** is a physical safe-deposit box or equivalent secure
storage. Its precise location is intentionally not disclosed publicly
to reduce attack surface; the existence and contents are documented
here so a successor knows what to look for.

The **legal heir** is designated in the maintainer's will with the
legal rights necessary to claim each asset (account-recovery process,
domain transfer, registry-account succession). Names are not published
to reduce social-engineering surface.

### 7.3 The 1-week procedure

In the event the maintainer is unreachable for **5 consecutive
business days** without explanation, or upon confirmed
incapacitation / death:

| Day | Step | Owner |
|---|---|---|
| 0 | Heir confirms the event and retrieves the lockbox. | Heir |
| 1–2 | Heir contacts GitHub Support invoking the deceased-user / unresponsive-user procedure; submits identity-verification documents from the lockbox; requests repo-ownership transfer to a successor account (heir or a designated successor maintainer named in the will). | Heir + GitHub Support |
| 3 | Successor account opens a public issue titled `[GOVERNANCE] Maintainer succession — <date>` and a corresponding GitHub Discussion. Community can resume opening / closing issues. | Successor |
| 4–5 | Successor invites a second admin so the post-event bus factor does not stay at 1. The second admin is chosen from the candidate list maintained out-of-band by the heir. | Successor |
| 6–7 | If any security advisory is pending, successor cuts a `vX.Y.Z+1` patch release. Otherwise, successor cuts a `vX.Y.Z` re-tagged release with updated maintainer information so downstream consumers can verify the chain of custody. | Successor |

This procedure is testable. A **shadow-handover dry run** will be
conducted annually starting in v0.4: the heir walks through the
GitHub-Support contact step with mock credentials, the successor
opens a draft governance-succession issue, and the maintainer
verifies the timeline holds. The dry-run result lands as a handover
document under `docs/handovers/`.

### 7.4 Timeline to MET

| Milestone | Target | Status |
|---|---|---|
| Designate legal heir in writing (will or equivalent legal instrument) | 2026-Q3 | Planned |
| Establish lockbox (safe-deposit box or equivalent) | 2026-Q3 | Planned |
| Deposit recovery kit (credentials, recovery codes, identity docs) into lockbox | 2026-Q3 | Planned |
| Brief heir on the §7.3 procedure (one-page printed sheet inside the lockbox) | 2026-Q3 | Planned |
| First annual shadow-handover dry-run | 2027-Q1 | Planned |
| Flip §7 status to MET on `bestpractices.dev` | After milestones above | Planned |

The maintainer updates this table by amendment PR (§9) as each
milestone completes. Until the lockbox is deposited and the heir is
briefed, this criterion remains UNMET — honest gap disclosure here
follows the same pattern as `docs/security/ASSURANCE_CASE.md` §6.

---

## 8. Bus factor

> **OpenSSF criterion `bus_factor`** (SHOULD): The project SHOULD have
> a bus factor of 2 or more.
>
> **Current status (2026-05-20): UNMET — bus factor is 1.** This is a
> SHOULD criterion, not MUST; the OpenSSF silver tier accepts UNMET
> SHOULD criteria with justification. The justification, mitigation,
> and target date are below.

### 8.1 Current state

Exactly one person currently has:

- GitHub admin permission on `Hashevolution/James-RAG-Evol`
- Authority to merge PRs to `main`
- Authority to cut releases
- Custodial knowledge of design intent (mother-platform thesis,
  trust-zone semantics, plugin contract draft)

That person is Jiwon Seo (`@Hashevolution`). **Bus factor = 1.**

### 8.2 Why bus factor is 1 today

The project is in **deliberate single-maintainer mode through v1.0**
(see §1, "Why BDFL through v1.0"). The mother-platform contract —
what `core/` exports, what trust zones exist, what plugins may assume
— requires a coherent decision-maker. Adding a second maintainer
before the contract is stable risks **contract drift** (CLAUDE.md
"no parallel domains" rule), which we have judged to be a larger risk
than bus factor at v0.3.x.

This is the project's reasoned trade-off, not negligence. It is also
a tractable trade-off: the timeline in §8.4 commits to bus factor ≥ 2
no later than the v1.0 transition.

### 8.3 What we do today to compensate

Even at bus factor 1, the following practices reduce the cost of a
loss-of-maintainer event. They do not raise the bus factor numerically;
they reduce the **recovery effort** at bus factor 1.

- **Comprehensive written reasoning.** Every PR carries a Summary +
  Verification + Out of scope. Every release has notes
  (`docs/release_notes_vX.Y.Z.md`). Every cycle has a handover under
  `docs/handovers/`. A successor reading these can reconstruct
  project intent without the maintainer.
- **Public 12-month-forward roadmap** (`ROADMAP.md`). A successor can
  pick up the next milestone without guessing.
- **Public architecture + non-goals** (`docs/ARCHITECTURE.md`) and
  **public readiness framework** (`docs/PLATFORM_READINESS.md`) capture
  the contract a successor must protect.
- **Security assurance case** (`docs/security/ASSURANCE_CASE.md`)
  with file:line citations into the codebase, so a successor can
  audit security properties without re-deriving them.
- **CLA with relicensing grant** (`docs/legal/CLA.md` §4-bis) means
  the project can be relicensed or forked-and-continued by a successor
  without re-contacting every past contributor.
- **CLAUDE.md operating rules** are normative even for a new
  maintainer: they encode the load-bearing constraints (rule 1 no
  domains, rule 2 bench numbers, rule 3 self-evolution opt-in, rule 4
  architecture-label PRs, rule 5 20 KB module cap, rule 6 no
  PolicyEngine bypass).

### 8.4 Plan to reach bus factor ≥ 2

| Milestone | Target | Status |
|---|---|---|
| Identify a second reviewer (read-only initially) from the contributor pool or external collaborator | 2026-Q4 | Planned |
| Grant second reviewer the GitHub **Triage** role (close / comment / label, no merge) | 2026-Q4 | Planned |
| First substantive non-maintainer-authored PR merged | 2027-Q1 | Planned (depends on community uptake) |
| Promote second reviewer to a **Maintainer** role with PR-merge authority on non-trust-boundary files | v0.4 → v1.0 transition | Planned |
| Bus factor formally 2 (two GitHub admins) | v1.0 launch or 2027-Q3, whichever is sooner | Planned |
| Flip §8 status to MET on `bestpractices.dev` | After milestones above | Planned |

The second admin will be invited from the contributor pool once it
materializes, or from a separately-recruited collaborator if the
contributor pool does not produce a candidate by 2027-Q1. The choice
of candidate is itself a §3 Class C decision (governance change),
recorded by amendment PR.

---

## 9. Amendments

This document is amended by Class C decision (see §3). Each amendment
PR must:

- Use the `governance` label.
- Open a 7-day comment window.
- Record the previous version's hash (git rev-parse HEAD of this file
  before the change) in the PR body so amendments are auditable.

The amendment history is the git log of this file. Section numbering
is stable — new sections are added at the next free number rather than
inserted, so external links to `#section-N` (notably the badge
submission URLs for §7 access continuity and §8 bus factor) remain
valid across future amendments.

---

## 한국어 요약

PROJECT JAMES는 v1.0까지 단일 메인테이너(BDFL) 모델로 운영합니다. 모든
설계·릴리스·라이선스 결정은 메인테이너인 서지원(`@Hashevolution`)에게
종결되며, 결정의 *근거*는 PR 설명·CHANGELOG·`docs/handovers/`에
기록됩니다. v1.0 이후 다중 메인테이너·도메인 팩 소유 모델로 전환할
예정이며, 전환 계획은 `docs/PLATFORM_READINESS.md`에 기록됩니다.

§7 **Access continuity** 와 §8 **Bus factor** 는 OpenSSF Best Practices
실버 티어 기준을 위해 작성되었습니다. 두 항목 모두 현재 시점(2026-05-20)
에는 **UNMET** 으로 정직하게 표기되어 있으며, lockbox + 법적 인계 모델
(§7.2) 과 2명 이상 메인테이너 확보 계획(§8.4) 의 마일스톤이 완료되는
시점(목표: 2026-Q3 ~ v1.0) 에 단계적으로 MET 으로 전환합니다. 정직한
빈틈 공개는 `docs/security/ASSURANCE_CASE.md §6` 의 패턴을 따릅니다.

CoC 신고는 `karu-7@hanmail.net`, 보안 신고는 `SECURITY.md` 의 절차를
따릅니다. 거버넌스·라이선스 변경은 7일 공개 코멘트 기간을 두고
진행합니다.
