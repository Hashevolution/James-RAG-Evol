# JAMES — UI Information Architecture (IA) Contract

> One-page IA contract for the JAMES web surface. Defines how user-facing
> actions are grouped, named, and located. Implementation lives elsewhere;
> this file is the **shape** the UI must converge on.
>
> Status: draft. v0.3.0 Platform Skeleton track.
> Last updated: 2026-05-20.

---

## 1. Why this document exists

The current UI surface (4 HTML pages, 119 HTTP endpoints, 17 admin tabs,
~79 `data-action` handlers) has grown by accretion. Three concrete
symptoms:

- **`admin.html` is a 73 KB single page** holding 17 unrelated tabs
  (`dashboard, users, policy, entities, memory, patches, uploads, files,
  audit, proposals, evo-reports, character, knowledge, performance,
  learning, hardware, settings`). Operators, reviewers, and observers
  share one screen.
- **One workflow crosses pages**: Change Request proposal lives in
  `/workspace`, approval in `/admin`, raw audit in CLI. Users page-hop
  to finish a single intent.
- **Action naming is inconsistent**: `data-action` and `data-page`
  conventions differ per page, so the same verb (e.g. "approve") has no
  predictable form.

This document fixes the **structure** (where things go, how they are
named) without prescribing visual design.

---

## 2. The 5 IA areas

The UI is reorganized around **user intent**, not API shape. Five areas,
mutually exclusive, collectively exhaustive:

| # | Area | Audience | Intent verb | Examples |
|---|---|---|---|---|
| 1 | **Ask** | end user | "I want an answer" | chat, sessions, history, feedback |
| 2 | **My Work** | end user | "manage my own artifacts" | my files, my jobs, my CR proposals, my API keys |
| 3 | **Govern** | reviewer / admin | "decide what changes" | CR approval, patch approval, proposal review, user approval, policy matrix |
| 4 | **Observe** | reviewer / admin | "see what happened / is happening" | audit log, trace replay, metrics, performance history, bench |
| 5 | **Configure** | admin | "set how the system behaves" | LLM selection, web-search, persona, character, hardware, learning rules, settings |

Diagram:

```
   ┌───────────────────────────────────────────────────────────────┐
   │                          End user                             │
   │   ┌──────────────┐                ┌────────────────────────┐  │
   │   │     Ask      │ ──────────────▶│        My Work         │  │
   │   │  (chat/QA)   │   produces     │  (files, jobs, CRs)    │  │
   │   └──────────────┘    artifacts   └───────────┬────────────┘  │
   │                                               │ proposes      │
   └───────────────────────────────────────────────┼───────────────┘
                                                   ▼
   ┌───────────────────────────────────────────────────────────────┐
   │                       Reviewer / admin                        │
   │   ┌────────────────┐   ┌────────────────┐   ┌──────────────┐  │
   │   │    Govern      │   │    Observe     │   │  Configure   │  │
   │   │ (approve/deny) │◀──│ (audit/trace)  │   │ (set policy) │  │
   │   └────────────────┘   └────────────────┘   └──────────────┘  │
   └───────────────────────────────────────────────────────────────┘
```

Rule of thumb: if a screen lets a user **change a thing they own**, it's
*My Work*; if it lets them **decide on a thing the system proposes**,
it's *Govern*; if it lets them **read history**, it's *Observe*; if it
lets them **set defaults**, it's *Configure*.

---

## 3. Current → Target mapping

### 3.1 Top-level pages

| Today | Tomorrow | Notes |
|---|---|---|
| `/` (chat) | **`/ask`** (or keep `/`) | unchanged scope |
| `/workspace` | **`/my`** | rename for clarity; same scope |
| `/admin` (17 tabs) | **`/govern`** + **`/observe`** + **`/configure`** | split — see §3.2 |
| `/admin/graph` | **`/observe/graph`** | graph is a read view; edits go through CR |

### 3.2 admin.html 17-tab redistribution

| Current admin tab | Target area | Rationale |
|---|---|---|
| `dashboard` | Observe (landing) | summary of audit + metrics |
| `users` | Govern | approve/reject signups |
| `policy` | Configure | set RBAC/ABAC matrix |
| `entities` | Observe (read) + Govern (edit via CR) | entity edits already CR-gated |
| `memory` | Observe | episodic + long-term snapshot |
| `patches` | Govern | approve/reject patches |
| `uploads` | Observe | upload history (read) |
| `files` | Govern *(admin actions)* / mirrored to My Work for own files | admin-wide file ops vs user-owned |
| `audit` | Observe | append-only log |
| `proposals` | Govern | approve/reject self-evolution proposals |
| `evo-reports` | Observe | evolution history |
| `character` | Configure | persona/tone defaults |
| `knowledge` | Observe | ability-growth view |
| `performance` | Observe | real-time + history metrics |
| `learning` | Configure | learning rules + topic seeds |
| `hardware` | Configure | LLM hw selection (first-run wizard lives here) |
| `settings` | Configure | global settings |

Result: **17 flat tabs → 3 pages (Govern: 5 / Observe: 8 / Configure: 5)**.
Mixed-mode tabs (`entities`, `files`) appear in two areas with **distinct
read vs write affordances**, not duplicated screens.

### 3.3 Cross-page workflows that must stop crossing pages

| Workflow | Today | Target |
|---|---|---|
| Change Request lifecycle | propose @ `/workspace`, approve @ `/admin`, audit @ CLI | propose @ **My Work**, approve @ **Govern**, audit @ **Observe** — but each step **links** to the next; no page-hop without a hand-off link |
| Self-evolution feedback loop | feedback @ `/`, proposals @ `/admin`, bench @ CLI | feedback @ **Ask**, proposals @ **Govern**, bench @ **Observe** (read-only mirror) |
| Trace investigation | trace_id surfaces in `/` answer, replay only via `scripts/replay_trace.py` | every answer in **Ask** carries a deep-link into **Observe → Trace** |

---

## 4. Naming conventions

### 4.1 `data-action` (button / link verbs)

Format: `<area>:<noun>:<verb>` (kebab-case, lowercase).

Examples:

- `ask:session:new`
- `ask:message:send`
- `my:cr:propose`
- `my:job:run`
- `govern:cr:approve`
- `govern:cr:reject`
- `govern:patch:approve`
- `observe:trace:open`
- `configure:llm:select`

Migration path: keep current `data-action` values working via an alias
map; emit a console warning when the legacy form is used; remove
warnings + aliases at the next minor.

### 4.2 `data-page` / route slugs

Format: `<area>` or `<area>/<subpage>` (lowercase, no underscores).

- `/ask`, `/my`, `/govern`, `/observe`, `/configure`
- Sub-pages: `/govern/proposals`, `/observe/audit`, `/configure/llm`

### 4.3 API endpoints

**Out of scope for this doc.** Existing 119 endpoints stay as-is. The
UI layer maps area pages to current endpoints. An API rename is a
separate v0.4 candidate.

---

## 5. What this doc deliberately does not decide

- Visual design system (colors, components, spacing) — comes after IA
- Framework choice (vanilla JS vs Vue vs Svelte) — orthogonal
- API endpoint renaming — separate contract
- Mobile / responsive strategy — out of scope for v0.3
- i18n string reorganization — follows once `data-action` names settle

---

## 6. Acceptance criteria for "IA is done"

This contract is satisfied when:

1. Every user-facing screen lives under exactly one of {Ask, My Work,
   Govern, Observe, Configure}.
2. `admin.html` no longer exists as a 17-tab monolith.
3. Every `data-action` matches `<area>:<noun>:<verb>`.
4. The three cross-page workflows in §3.3 each have explicit hand-off
   links between pages (no silent page-hops).
5. A new contributor can place a new screen into the correct area from
   reading this doc alone, without asking.

---

## 7. Out-of-scope confirmation (per `CLAUDE.md`)

This IA is **platform-level** (mother-hardening), not a domain feature.
No legal / food / retail / travel / finance specialization is implied
or unlocked by this restructure. Domain forks remain post-v1.0 only.

---

## 한국어 요약

JAMES의 UI는 4페이지·119 API·17탭이 누적되며 "중구난방"이 됐습니다. 이
문서는 **사용자 의도** 기준으로 5영역(Ask / My Work / Govern / Observe /
Configure)을 확정하고, 현재 `/admin` 단일 페이지의 17탭을 Govern·Observe·
Configure 3페이지로 재분배합니다. CR 제안→승인→감사 같은 작업이 페이지를
가로질러 흩어진 문제는 **명시적 hand-off 링크**로 해소합니다. `data-action`
명명은 `<영역>:<명사>:<동사>` 규칙으로 통일합니다. 시각 디자인·프레임워크
선택·API 리네이밍은 이 문서 범위 밖입니다.
