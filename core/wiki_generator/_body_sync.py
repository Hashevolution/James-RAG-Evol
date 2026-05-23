"""Sync the wiki body's `## 요약` section to a canonical summary string.

Shared by two call sites:

- ``scripts/resync_wiki_summary_body.py`` — one-shot backlog migration
  that rewrites every stale `## 요약` block on disk to match its
  frontmatter top-level ``summary``.
- ``core.graph_node_editor.update_node_attributes`` — runtime UI edits.
  Pre-PR-#446 the editor only patched the frontmatter, so a "Save"
  from the graph node detail panel changed `summary:` in the yaml
  header but left the visible `## 요약` body section untouched —
  exactly the regression surfaced in 2026-05-24 Stage E.1 (B-2 graph
  follow-up).

Pulled into its own module so both call sites share one regex, one
whitespace convention, and one idempotency contract. If the body
window evolves later (e.g. `## 본문` instead of `## 요약`), only this
file moves.
"""

from __future__ import annotations

import re
from typing import Tuple

# `## 요약\n<content>\n## 관계` — DOTALL so `.` spans newlines, non-greedy
# so we stop at the first `## 관계` (the only section that ever follows
# `## 요약` in the wiki body template).
_BODY_PAT = re.compile(r"(## 요약\n)(.*?)(\n## 관계)", re.DOTALL)


def sync_summary_body(body: str, summary: str) -> Tuple[str, bool]:
    """Rewrite the `## 요약` body window to contain `summary`.

    Returns ``(new_body, changed)``.

    - ``changed=False`` when the body already matches (idempotent), or
      when the `## 요약 ... ## 관계` window isn't present (caller decides
      what to do — the runtime path leaves it alone, the resync script
      skips the file).
    - ``summary`` may be empty — that leaves the section header but
      with blank content, matching the new-entity shape produced by
      ``create_entity_file`` when no summary is supplied.
    """
    m = _BODY_PAT.search(body)
    if not m:
        return body, False
    current = m.group(2).strip()
    if current == summary.strip():
        return body, False
    spacer = "\n" if summary else ""
    new = _BODY_PAT.sub(
        lambda mm: mm.group(1) + summary + spacer + mm.group(3),
        body,
        count=1,
    )
    return new, True
