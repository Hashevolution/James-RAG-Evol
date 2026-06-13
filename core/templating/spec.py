"""Parse raw template text into a normalized, domain-agnostic spec.

A ``TemplateSpec`` is the structure JAMES extracts from a user-supplied
template. It carries *no* domain knowledge — only the shape the author
laid out: ordered sections, fill-in placeholders, and optional per-line
hints. ``core/templating/formatter.py`` consumes the spec to build the
reshaping prompt.

The template text is **untrusted data**. Nothing here executes or
interprets imperative text inside a template; parsing only detects
structure. See ``docs/design/v0.6-template-formatting-ui.md`` §4/§7.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# ``{{name}}`` / ``{name}`` / ``[name]`` fill-in slots. Names are kept
# verbatim (after strip); we do not constrain their charset because a
# placeholder name is content, not a path/id.
_PLACEHOLDER_RES = (
    re.compile(r"\{\{\s*([^{}]+?)\s*\}\}"),   # {{ name }}
    re.compile(r"(?<!\{)\{\s*([^{}]+?)\s*\}(?!\})"),  # { name } (not {{ }})
    re.compile(r"\[\s*([^\[\]]+?)\s*\]"),     # [ name ]
)

# Markdown ATX heading: 1-6 leading '#', then text.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# ``Label:`` style section header — a short label followed by a colon at
# end-of-line (no trailing value on the same line). Kept conservative so
# ordinary prose with a colon mid-sentence is not mistaken for a header.
_LABEL_RE = re.compile(r"^\s*([^\n:]{1,60}):\s*$")


@dataclass
class Section:
    """One detected section / labelled block in a template."""

    title: str
    level: int = 1          # markdown heading depth; 1 for Label: blocks
    kind: str = "heading"   # "heading" | "label"


@dataclass
class TemplateSpec:
    """Normalized structure extracted from raw template text.

    Attributes:
      raw:          the original template text, verbatim.
      sections:     ordered detected sections (declaration order).
      placeholders: unique fill-in slot names, first-seen order.
    """

    raw: str
    sections: List[Section] = field(default_factory=list)
    placeholders: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sections": [
                {"title": s.title, "level": s.level, "kind": s.kind}
                for s in self.sections
            ],
            "placeholders": list(self.placeholders),
        }


def _extract_placeholders(text: str) -> List[str]:
    """Return unique placeholder names in first-seen (text-position) order."""
    found = []  # (start_pos, name)
    for pattern in _PLACEHOLDER_RES:
        for m in pattern.finditer(text):
            name = (m.group(1) or "").strip()
            if name:
                found.append((m.start(), name))
    found.sort(key=lambda t: t[0])
    seen: List[str] = []
    seen_set = set()
    for _, name in found:
        if name not in seen_set:
            seen_set.add(name)
            seen.append(name)
    return seen


def _extract_sections(text: str) -> List[Section]:
    """Detect markdown headings and ``Label:`` blocks, in order."""
    sections: List[Section] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            sections.append(
                Section(title=m.group(2).strip(),
                        level=len(m.group(1)),
                        kind="heading")
            )
            continue
        m = _LABEL_RE.match(line)
        if m:
            label = m.group(1).strip()
            # A markdown heading also ends with non-colon text, so the
            # heading branch above already consumed those; here we only
            # see bare ``Label:`` lines.
            if label:
                sections.append(
                    Section(title=label, level=1, kind="label")
                )
    return sections


def parse_template(raw_text: str) -> TemplateSpec:
    """Parse ``raw_text`` into a :class:`TemplateSpec`.

    Pure function of the input — deterministic, no I/O, no side effects.
    Imperative-looking text inside the template is *not* interpreted;
    only structural markers (headings, ``Label:`` lines, placeholders)
    are detected.
    """
    text = raw_text or ""
    return TemplateSpec(
        raw=text,
        sections=_extract_sections(text),
        placeholders=_extract_placeholders(text),
    )


__all__ = ["Section", "TemplateSpec", "parse_template"]
