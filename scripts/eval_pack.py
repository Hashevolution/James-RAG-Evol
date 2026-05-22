"""Pack eval contract — Track C PR-C9.

Runs the v0.3 minimum-viable eval gate against ``packs/<name>/``.
Designed for two callers:

  1. **CI** (``.github/workflows/packs-eval.yml``) — invokes this per
     changed pack on every PR that touches ``packs/``. Exit code is
     the gate signal: 0 = pass, non-zero = block the merge.

  2. **Pack authors locally** — same exit code; use it as a
     pre-PR self-check (``docs/PLUGIN_AUTHORING.md`` §6).

What the gate checks **in v0.3**:

  - ``packs/<name>/`` directory exists
  - ``pack.yaml`` parses + every required manifest field is well-typed
  - ``james_api:`` SemVer range contains the running JAMES core version
  - Each declared slot import path resolves; the class instantiates;
    the instance satisfies the Protocol via ``isinstance``
  - The pack passes ``ruff check`` (style + obvious errors)

What this gate does **NOT yet check** (deferred until CI has the
underlying infrastructure):

  - **RAGAS retrieval-quality eval** — requires an LLM endpoint
    available to the CI runner. JAMES CI has no Ollama service today.
    Pack authors run RAGAS locally per ``docs/PLUGIN_AUTHORING.md``
    §6 until CI gets the Ollama service container.
  - **STEP-N regression bench** — same constraint. The committed
    baseline (``eval/regression/step7_baseline.json``) is the
    authoritative number; pack authors compare locally and paste the
    diff in the PR body per CLAUDE.md rule #2.

When CI gains an LLM endpoint, this script grows ``--with-ragas``
and ``--with-step`` flags that the workflow lights up. The contract
shape is stable now; only the gate's bite gets sharper.

Usage::

    python scripts/eval_pack.py <pack_name>           # full v0.3 gate
    python scripts/eval_pack.py <pack_name> --manifest-only
    python scripts/eval_pack.py --all                 # every pack on disk
"""
from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    # Windows console + Korean text in pack manifests = UnicodeEncodeError
    # unless we reset the codepage. utils/console.py is the project's
    # single source of truth for this.
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass

from core.plugins.base import (  # noqa: E402
    OntologyPack,
    PromptPack,
    Scorer,
    UIPanel,
)
from core.plugins.errors import (  # noqa: E402
    PluginLoadError,
    PluginVersionError,
)
from core.plugins.loader import JAMES_CORE_VERSION  # noqa: E402
from core.plugins.manifest import (  # noqa: E402
    Manifest,
    check_semver,
    read_manifest,
)

PACKS_ROOT = ROOT / "packs"

# Maps slot name -> the Protocol type the isinstance check uses.
_PROTOCOL_MAP = {
    "ontology": OntologyPack,
    "prompts": PromptPack,
    "ui": UIPanel,
    "scorers": Scorer,
}


class PackEvalFailure(Exception):
    """Operator-visible failure during eval. The message is what the
    operator (or pack author) sees in the CI log; keep it actionable.
    """


def _ok(line: str) -> None:
    print(f"  OK    {line}")


def _fail(line: str) -> None:
    print(f"  FAIL  {line}", file=sys.stderr)


def _check_manifest(pack_name: str) -> Manifest:
    pack_dir = PACKS_ROOT / pack_name
    if not pack_dir.is_dir():
        raise PackEvalFailure(
            f"pack {pack_name!r} not found at {pack_dir}"
        )
    pack_yaml = pack_dir / "pack.yaml"
    try:
        manifest = read_manifest(pack_yaml, pack_name)
    except PluginLoadError as exc:
        raise PackEvalFailure(f"manifest parse: {exc}") from exc
    _ok(f"manifest parses: {manifest.name} v{manifest.version} ({manifest.license})")

    try:
        check_semver(pack_name, manifest.james_api, JAMES_CORE_VERSION)
    except PluginVersionError as exc:
        raise PackEvalFailure(f"SemVer: {exc}") from exc
    except PluginLoadError as exc:
        raise PackEvalFailure(f"SemVer parse: {exc}") from exc
    _ok(f"james_api {manifest.james_api!r} contains core {JAMES_CORE_VERSION!r}")

    return manifest


def _check_slot_imports(pack_name: str, manifest: Manifest) -> None:
    if not manifest.plugins:
        print(f"  WARN  pack {pack_name!r} declares zero slots (legal but unusual)")
        return

    pack_dir = PACKS_ROOT / pack_name
    pack_dir_str = str(pack_dir)
    sys.path.insert(0, pack_dir_str)
    try:
        for slot, value in manifest.plugins.items():
            entries: List[str] = (
                [value] if isinstance(value, str) else list(value)
            )
            protocol_type = _PROTOCOL_MAP.get(slot)
            if protocol_type is None:
                # Manifest parser already rejects unknown slots; defensive.
                raise PackEvalFailure(
                    f"slot {slot!r} has no Protocol mapping; "
                    f"this is a JAMES core bug, not a pack bug"
                )
            for import_path in entries:
                module_path, class_name = import_path.split(":", 1)
                try:
                    module = importlib.import_module(module_path)
                except ImportError as exc:
                    raise PackEvalFailure(
                        f"slot={slot} cannot import {module_path!r} "
                        f"from {pack_dir}: {exc}"
                    ) from exc
                if not hasattr(module, class_name):
                    raise PackEvalFailure(
                        f"slot={slot} module {module_path!r} has no "
                        f"class {class_name!r}"
                    )
                cls = getattr(module, class_name)
                try:
                    instance = cls()
                except Exception as exc:  # noqa: BLE001 — wrap with context
                    raise PackEvalFailure(
                        f"slot={slot} instantiating "
                        f"{module_path}:{class_name} raised "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
                if not isinstance(instance, protocol_type):
                    raise PackEvalFailure(
                        f"slot={slot} {module_path}:{class_name} does "
                        f"not satisfy {protocol_type.__name__} Protocol"
                    )
                _ok(
                    f"slot={slot} {module_path}:{class_name} -> "
                    f"{protocol_type.__name__} satisfied"
                )
    finally:
        try:
            sys.path.remove(pack_dir_str)
        except ValueError:
            pass


def _check_ruff(pack_name: str) -> None:
    pack_dir = PACKS_ROOT / pack_name
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(pack_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        # ruff not installed — surface clearly. The CI workflow
        # installs ruff via requirements-dev-equivalent; locally an
        # operator might be missing it.
        raise PackEvalFailure(
            f"ruff not available: {exc}. Install with `pip install ruff`."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PackEvalFailure(f"ruff timed out after 60s: {exc}") from exc
    if result.returncode != 0:
        # Pass ruff's own output through — the messages are already
        # actionable (file:line:col).
        if result.stdout:
            sys.stderr.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        raise PackEvalFailure(
            f"ruff check failed on packs/{pack_name}/ "
            f"(exit {result.returncode})"
        )
    _ok(f"ruff check passes on packs/{pack_name}/")


def evaluate_pack(pack_name: str, *, manifest_only: bool = False) -> Tuple[bool, str]:
    """Run the gate on one pack. Returns (passed, summary_line).

    The summary_line is suitable for the CI step summary or a local
    one-line print.
    """
    print(f"[eval-pack] {pack_name}")
    try:
        manifest = _check_manifest(pack_name)
        if not manifest_only:
            _check_slot_imports(pack_name, manifest)
            _check_ruff(pack_name)
    except PackEvalFailure as exc:
        _fail(str(exc))
        return False, f"{pack_name}: FAIL — {exc}"
    summary = f"{pack_name}: PASS (v{manifest.version}, {manifest.license})"
    print(f"[eval-pack] {summary}")
    return True, summary


def _discover_packs() -> List[str]:
    if not PACKS_ROOT.is_dir():
        return []
    return sorted(p.name for p in PACKS_ROOT.iterdir() if p.is_dir())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pack eval gate — v0.3 minimum-viable contract."
    )
    parser.add_argument(
        "pack", nargs="?",
        help="Pack name (directory under packs/). Required unless --all.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Evaluate every pack under packs/ in sorted order.",
    )
    parser.add_argument(
        "--manifest-only", action="store_true",
        help="Skip slot-import and ruff checks; manifest schema only.",
    )
    args = parser.parse_args()

    if args.all and args.pack:
        parser.error("--all and an explicit pack name are mutually exclusive")
    if not args.all and not args.pack:
        parser.error("either pass a pack name or --all")

    targets = _discover_packs() if args.all else [args.pack]
    if not targets:
        print(
            "[eval-pack] no packs found under packs/; "
            "v0.3 dogfood pack lives at packs/general/ (PR-C5a #413)"
        )
        return 1

    all_pass = True
    summaries: List[str] = []
    for name in targets:
        ok, line = evaluate_pack(name, manifest_only=args.manifest_only)
        summaries.append(line)
        all_pass = all_pass and ok

    print()
    print("-" * 60)
    print("[eval-pack] summary:")
    for line in summaries:
        print(f"  {line}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
