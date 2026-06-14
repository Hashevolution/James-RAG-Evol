"""6 built-in agent tools (v0.6.1 Phase C).

Each tool wraps an existing Phase 5.5 building block when one fits
(`tools/code/read_file.py`, `tools/code/code_editor.py`) and falls
back to a direct os/io call otherwise. Every tool calls
``policy_validate_path`` so the path safety contract is enforced even
if the dispatcher is bypassed.

Tool surface intentionally mirrors what Claude Code's first-party
tools expose (list / read / write / edit / glob / grep) so an LLM
trained on that surface has familiar handles.
"""
from __future__ import annotations

import fnmatch
import os
import re
from typing import Any, Dict, List

from core.agent_tools.registry import Tool, ToolError, register_tool


def _validate(path: str, role: str) -> str:
    """Run the Phase 5.5 sandbox path guard. Raises ``ToolError`` so
    the dispatcher surfaces an LLM-facing error."""
    from tools.code.sandbox import validate_path
    ok, msg = validate_path(path, role=role)
    if not ok:
        raise ToolError(f"path rejected: {msg}")
    return path


# ── list_files ──────────────────────────────────────────────────

def _h_list_files(args: Dict[str, Any], role: str) -> List[Dict[str, Any]]:
    path = args.get("path") or ""
    if not isinstance(path, str) or not path:
        raise ToolError("'path' (string) is required")
    _validate(path, role)
    if not os.path.isdir(path):
        raise ToolError(f"not a directory: {path!r}")
    entries: List[Dict[str, Any]] = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            try:
                is_dir = os.path.isdir(full)
                size = 0 if is_dir else os.path.getsize(full)
            except OSError:
                continue
            entries.append({"name": name, "is_dir": is_dir, "size": size})
    except OSError as e:
        raise ToolError(f"listdir failed: {e}")
    # Cap so the LLM context doesn't drown on huge dirs.
    return entries[:500]


register_tool(Tool(
    name="list_files",
    description=(
        "List entries (files + subdirs) in a directory the operator "
        "has allowed. Returns up to 500 entries."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Absolute path to a directory the agent is allowed to read."},
        },
        "required": ["path"],
    },
    handler=_h_list_files,
))


# ── read_file ───────────────────────────────────────────────────

def _h_read_file(args: Dict[str, Any], role: str) -> Dict[str, Any]:
    path = args.get("path") or ""
    if not isinstance(path, str) or not path:
        raise ToolError("'path' (string) is required")
    _validate(path, role)
    if not os.path.isfile(path):
        raise ToolError(f"not a file: {path!r}")
    try:
        # Mirror the read_file.py tool's 500 KB cap so the LLM never
        # ingests megabytes of binary unintended.
        max_bytes = 500 * 1024
        size = os.path.getsize(path)
        if size > max_bytes:
            raise ToolError(f"file too large ({size} bytes > {max_bytes})")
        with open(path, "rb") as f:
            data = f.read()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ToolError("file is not valid UTF-8 text")
    except OSError as e:
        raise ToolError(f"read failed: {e}")
    return {"path": path, "bytes": size, "content": text}


register_tool(Tool(
    name="read_file",
    description=(
        "Read a UTF-8 text file from an allowed path. 500 KB cap; "
        "binary or oversize files surface as an error."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    },
    handler=_h_read_file,
    audit_post_call=False,   # output is the file body — keep audit compact
))


# ── write_file ──────────────────────────────────────────────────

def _h_write_file(args: Dict[str, Any], role: str) -> Dict[str, Any]:
    path = args.get("path") or ""
    content = args.get("content")
    if not isinstance(path, str) or not path:
        raise ToolError("'path' (string) is required")
    if not isinstance(content, str):
        raise ToolError("'content' (string) is required")
    _validate(path, role)
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        raise ToolError(f"parent directory does not exist: {parent!r}")
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    except OSError as e:
        raise ToolError(f"write failed: {e}")
    return {"path": path, "bytes": len(content.encode("utf-8"))}


register_tool(Tool(
    name="write_file",
    description=(
        "Write (or overwrite) a UTF-8 text file at an allowed path. "
        "Parent directory must already exist."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
    handler=_h_write_file,
))


# ── edit_file (substring replace) ───────────────────────────────

def _h_edit_file(args: Dict[str, Any], role: str) -> Dict[str, Any]:
    path = args.get("path") or ""
    old = args.get("old_string")
    new = args.get("new_string")
    replace_all = bool(args.get("replace_all", False))
    if not isinstance(path, str) or not path:
        raise ToolError("'path' (string) is required")
    if not isinstance(old, str) or not isinstance(new, str):
        raise ToolError("'old_string' and 'new_string' (strings) are required")
    if not old:
        raise ToolError("'old_string' must be non-empty")
    _validate(path, role)
    if not os.path.isfile(path):
        raise ToolError(f"not a file: {path!r}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise ToolError(f"read failed: {e}")
    count = text.count(old)
    if count == 0:
        raise ToolError("old_string not found in file")
    if count > 1 and not replace_all:
        raise ToolError(
            f"old_string is not unique ({count} matches); "
            "pass replace_all=true or use a more specific snippet"
        )
    new_text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
    except OSError as e:
        raise ToolError(f"write failed: {e}")
    return {
        "path": path,
        "replaced": count if replace_all else 1,
        "delta_bytes": len(new_text.encode("utf-8")) - len(text.encode("utf-8")),
    }


register_tool(Tool(
    name="edit_file",
    description=(
        "Replace ``old_string`` with ``new_string`` in a file. By "
        "default requires the match to be unique; set "
        "``replace_all: true`` to replace every occurrence."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        "required": ["path", "old_string", "new_string"],
    },
    handler=_h_edit_file,
))


# ── glob_files ──────────────────────────────────────────────────

def _h_glob_files(args: Dict[str, Any], role: str) -> List[str]:
    pattern = args.get("pattern") or ""
    root = args.get("path") or ""
    if not isinstance(pattern, str) or not pattern:
        raise ToolError("'pattern' (string) is required")
    if not isinstance(root, str) or not root:
        raise ToolError("'path' (string) is required")
    _validate(root, role)
    if not os.path.isdir(root):
        raise ToolError(f"not a directory: {root!r}")
    matches: List[str] = []
    # `pattern` may contain a path component (e.g. "src/**/*.py"). We
    # treat it as fnmatch against the *relative* path.
    for dirpath, _dirs, files in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for name in files:
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            if fnmatch.fnmatch(rel, pattern):
                matches.append(os.path.join(dirpath, name))
                if len(matches) >= 500:
                    return matches
    return matches


register_tool(Tool(
    name="glob_files",
    description=(
        "Find files under ``path`` whose relative path matches "
        "``pattern`` (fnmatch syntax — ``*.md``, ``src/**/*.py``, …). "
        "Caps at 500 results."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["pattern", "path"],
    },
    handler=_h_glob_files,
))


# ── grep_files ──────────────────────────────────────────────────

def _h_grep_files(args: Dict[str, Any], role: str) -> List[Dict[str, Any]]:
    pattern = args.get("pattern") or ""
    root = args.get("path") or ""
    case_insensitive = bool(args.get("case_insensitive", False))
    if not isinstance(pattern, str) or not pattern:
        raise ToolError("'pattern' (regex string) is required")
    if not isinstance(root, str) or not root:
        raise ToolError("'path' (string) is required")
    _validate(root, role)
    if not os.path.isdir(root):
        raise ToolError(f"not a directory: {root!r}")
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        rgx = re.compile(pattern, flags)
    except re.error as e:
        raise ToolError(f"bad regex: {e}")
    hits: List[Dict[str, Any]] = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(dirpath, name)
            try:
                if os.path.getsize(full) > 1 * 1024 * 1024:
                    continue   # skip > 1 MB
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    for line_no, line in enumerate(f, start=1):
                        if rgx.search(line):
                            hits.append({
                                "file": full,
                                "line": line_no,
                                "text": line.rstrip("\n")[:300],
                            })
                            if len(hits) >= 500:
                                return hits
            except OSError:
                continue
    return hits


register_tool(Tool(
    name="grep_files",
    description=(
        "Search for a regex inside text files under ``path``. Returns "
        "up to 500 ``{file, line, text}`` hits. Files larger than 1 MB "
        "are skipped."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
            "case_insensitive": {"type": "boolean"},
        },
        "required": ["pattern", "path"],
    },
    handler=_h_grep_files,
))
