"""Wiki generator — wiki-wide index/sweep operations.

``WikiIndexOpsMixin``: the three wiki-wide aggregation methods —
``update_index`` (rebuild index.md summary), ``get_entity_statistics``
(per-type entity counts), and ``resolve_pending_relations`` (the
UNRESOLVED → entity_id back-fill sweep).

Split out of ``_frontmatter.py`` so neither file exceeds the 20 KB
CLAUDE.md rule #5 gate. These methods all walk every entity-type
directory and operate at wiki scope (rather than the single-entity
writer responsibility that ``_frontmatter.py`` owns), so the seam
is also conceptually clean.

All three use ``self.<lower-layer method>`` (notably
``self._find_existing_entity_id`` from ``_frontmatter.py``) — mixin
composition in ``core/wiki_generator/__init__.py`` resolves them.
"""
from __future__ import annotations

import yaml


class WikiIndexOpsMixin:

    def update_index(self):
        total = 0
        lines = ["# INDEX\n"]

        for t in self.entity_types:
            d = self.entity_path / t
            count = len(list(d.glob("*.md"))) if d.exists() else 0
            total += count

            lines.append(f"\n## {t} ({count})")

        self.index_path.write_text("\n".join(lines), encoding="utf-8")

    def resolve_pending_relations(self) -> int:
        """
        frontmatter `relations:` 키의 `target_id == "UNRESOLVED"` 항목을
        현재 entity 인덱스로 재매칭하여 채워준다.

        Why frontmatter only:
          create_entity_file 이 권위로 사용하는 위치는 frontmatter
          `relations:` 키이다. body 의 `## 관계` 섹션은 사람-읽기용
          미러(예: `- 관련: FAA (conf=0.90)`)일 뿐 entity_id 를 노출하지
          않으므로 매칭과 무관 — 그대로 둔다.

        Why call this:
          create_entity_file 시점에 target entity 가 아직 ingest 되지
          않았으면 UNRESOLVED 로 남는다 (다른 PDF 가 늦게 들어오거나,
          같은 PDF 의 다른 entity 가 뒤에서 만들어지는 케이스). 본
          메서드를 entity_map refresh 직후 호출하면 그 시점까지 알려진
          모든 entity 와 매칭이 완성된다.

        Returns:
            갱신된 relation 항목의 누적 개수.
        """
        files_changed = 0
        relations_fixed = 0

        for t in self.entity_types:
            d = self.entity_path / t
            if not d.exists():
                continue

            for f in d.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                if not content.startswith("---"):
                    continue
                end = content.find("---", 3)
                if end < 0:
                    continue

                try:
                    fm = yaml.safe_load(content[3:end]) or {}
                except Exception as e:
                    print(f"[RESOLVE] YAML parse fail {f.name}: {e}")
                    continue

                body_tail = content[end + 3:]
                relations = fm.get("relations")
                if not isinstance(relations, list) or not relations:
                    continue

                file_changed = False
                for r in relations:
                    if not isinstance(r, dict):
                        continue
                    if r.get("target_id") != "UNRESOLVED":
                        continue
                    target = (r.get("target") or "").strip()
                    if not target:
                        continue
                    ttype = r.get("target_type")
                    # 정확 target_type 매칭 → 전체 타입 fallback
                    found = (
                        self._find_existing_entity_id(target, ttype)
                        or self._find_existing_entity_id(target, None)
                    )
                    if found:
                        r["target_id"] = found
                        file_changed = True
                        relations_fixed += 1

                if file_changed:
                    new_content = (
                        "---\n"
                        + yaml.dump(
                            fm,
                            allow_unicode    = True,
                            default_flow_style = False,
                            sort_keys        = True,
                        )
                        + "---"
                        + body_tail
                    )
                    f.write_text(new_content, encoding="utf-8")
                    files_changed += 1

        print(f"[RESOLVE] {files_changed} files updated, "
              f"{relations_fixed} relations resolved")
        return relations_fixed

    def get_entity_statistics(self):
        stats = {}
        total = 0

        for t in self.entity_types:
            d = self.entity_path / t
            c = len(list(d.glob("*.md"))) if d.exists() else 0
            stats[t] = c
            total += c

        stats["total"] = total
        return stats


__all__ = ["WikiIndexOpsMixin"]
