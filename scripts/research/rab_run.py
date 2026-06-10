"""R1.4 — Run the RAB benchmark for one SUT and write a result JSON
with the re-verification artifacts the pre-reg locks in.

Usage::

    python scripts/research/rab_run.py --sut james     [--engine]
    python scripts/research/rab_run.py --sut baseline0
    python scripts/research/rab_run.py --sut reference

Outputs (under ``reports/rab/``)::

    <sut>-<scenario>-<ts>.result.json   # the numbers + meta + sha
    <sut>-<scenario>-<ts>.log.jsonl     # exported audit log (artifact)
    <sut>-<scenario>-<ts>.mapping.json  # mapping table (artifact)

Per pre-reg (`docs/research/r1-4-preregistration-2026-06-10.md` §2),
result.json includes:

* spec, scenario, scenario_sha
* sut, sut_version (git sha)
* AC / RF / PC blocks (driver.score_run output)
* n_log_events
* log_sha, mapping_table_sha
* runner_env

Anyone with these three files + the SPEC + scenario fixture can re-run
the deterministic scorer and reproduce the numbers bit-for-bit
(SPEC §4).

Honest framing (pre-reg §4): the headline of a RAB release is the gap
table across SUTs, not any one number. This script writes per-SUT
artifacts; assembling the gap table is the operator's next step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from eval.rab.driver import load_scenario, run_scenario, score_run


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha256_file(p: Path) -> str:
    return _sha256_text(p.read_text(encoding="utf-8"))


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            stderr=subprocess.DEVNULL,
        ).decode("ascii").strip()
        return out
    except Exception:
        return "unknown"


def _build_adapter(sut: str, *, use_engine: bool, workspace: Path):
    if sut == "reference":
        from eval.rab.adapters.reference import ReferenceAdapter
        return ReferenceAdapter(), {}  # mapping table is canonical-native
    if sut == "baseline0":
        from eval.rab.adapters.baseline0 import Baseline0Adapter
        adapter = Baseline0Adapter()
        return adapter, Baseline0Adapter.MAPPING_TABLE
    if sut == "james":
        from eval.rab.adapters.james import JamesAdapter
        adapter = JamesAdapter(workspace=workspace, use_engine=use_engine)
        return adapter, JamesAdapter.MAPPING_TABLE
    raise SystemExit(f"unknown sut: {sut!r}")


def _runner_env() -> dict:
    return {
        "python":   sys.version.split()[0],
        "platform": platform.platform(),
        "ts_utc":   datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="rab_run")
    p.add_argument("--sut", required=True,
                    choices=["reference", "baseline0", "james"])
    p.add_argument("--scenario", default="S1",
                    help="scenario id (only S1 v0.1 ships today)")
    p.add_argument("--out-dir", default=str(ROOT / "reports" / "rab"))
    p.add_argument("--engine", action="store_true",
                    help="(james only) route query() through real "
                         "ReasoningEngine — requires Ollama running")
    p.add_argument("--workspace", default=None,
                    help="(james only) workspace dir; default = tmp")
    args = p.parse_args(argv)

    scenario_path = ROOT / "eval" / "rab" / "scenarios" \
                       / "s1_lifecycle_small.json"
    if args.scenario != "S1":
        raise SystemExit("only S1 ships in v0.1")

    scenario = load_scenario(scenario_path)
    scenario_sha = _sha256_file(scenario_path)

    ws = (Path(args.workspace) if args.workspace
          else Path(tempfile.mkdtemp(prefix="rab_run_")))
    adapter, mapping_table = _build_adapter(
        args.sut, use_engine=args.engine, workspace=ws,
    )

    print(f"[RAB] sut={args.sut} scenario={args.scenario} "
          f"workspace={ws}")
    if args.sut == "james" and args.engine:
        print("[RAB] JAMES engine mode — calling real ReasoningEngine "
              "for every QUERY op")

    artifacts = run_scenario(scenario, adapter)
    scores    = score_run(artifacts)

    # Persist artifacts (the re-verification bundle).
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{args.sut}-{args.scenario}-{stamp}"

    log_path     = out_dir / f"{stem}.log.jsonl"
    mapping_path = out_dir / f"{stem}.mapping.json"
    result_path  = out_dir / f"{stem}.result.json"

    log_text = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                         for r in artifacts["log"]) + "\n"
    log_path.write_text(log_text, encoding="utf-8")

    mapping_text = json.dumps(mapping_table, ensure_ascii=False,
                              sort_keys=True, indent=2)
    mapping_path.write_text(mapping_text, encoding="utf-8")

    result = {
        "spec":               "v0.1.1",
        "scenario":           args.scenario,
        "scenario_sha":       scenario_sha,
        "sut":                args.sut,
        "sut_version":        _git_sha(),
        "AC":                 scores["AC"],
        "RF":                 scores["RF"],
        "PC":                 scores["PC"],
        "n_log_events":       scores["n_log_events"],
        "log_sha":            _sha256_text(log_text),
        "mapping_table_sha":  _sha256_text(mapping_text),
        "runner_env":         _runner_env(),
        "engine_mode":        bool(args.engine and args.sut == "james"),
    }
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )

    print(f"[RAB] AC overall       = {scores['AC']['overall']}")
    print(f"[RAB] RF exact / graded = {scores['RF']['exact']} / "
          f"{scores['RF']['graded']}")
    print(f"[RAB] PC overall       = {scores['PC']['pc']}")
    print(f"[RAB] log events       = {scores['n_log_events']}")
    print(f"[RAB] artifacts saved  → {result_path}")
    print(f"[RAB]                   → {log_path}")
    print(f"[RAB]                   → {mapping_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
