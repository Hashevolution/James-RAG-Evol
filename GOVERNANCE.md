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

- **BDFL**: Hashevolution (`@Hashevolution` on GitHub), referred to in this
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
| **Maintainer** | Hashevolution | Reviews and merges PRs · sets roadmap · cuts releases · owns license decisions · enforces CoC | Force-push to `main` (avoided in practice) · approve security disclosures · sign releases |
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

## 7. Amendments

This document is amended by Class C decision (see §3). Each amendment
PR must:

- Use the `governance` label.
- Open a 7-day comment window.
- Record the previous version's hash in the PR body so amendments are
  auditable.

The amendment history is the git log of this file.

---

## 한국어 요약

PROJECT JAMES는 v1.0까지 단일 메인테이너(BDFL) 모델로 운영합니다. 모든
설계·릴리스·라이선스 결정은 메인테이너(Hashevolution)에게 종결되며,
결정의 *근거*는 PR 설명·CHANGELOG·`docs/handovers/`에 기록됩니다. v1.0
이후 다중 메인테이너·도메인 팩 소유 모델로 전환할 예정이며, 전환 계획은
`docs/PLATFORM_READINESS.md`에 기록됩니다. CoC 신고는
`karu-7@hanmail.net`, 보안 신고는 `SECURITY.md`의 절차를 따릅니다.
거버넌스·라이선스 변경은 7일 공개 코멘트 기간을 두고 진행합니다.
