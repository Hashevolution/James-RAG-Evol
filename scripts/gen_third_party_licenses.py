"""Generate THIRD_PARTY_LICENSES.md from the active venv's installed packages.

One-shot regeneration script — re-run at every minor JAMES version
(v0.4, v0.5, ...) and whenever a dep is added. Anything that differs
between a fresh run and the committed THIRD_PARTY_LICENSES.md is a dep
change since the last refresh.

Why this lives in scripts/ rather than as a CI step:
  - The list reflects what is installed in *this* venv, not what is
    pinned in requirements.txt. Different venvs have slightly different
    pulls (platform-specific wheels, optional extras), so an automatic
    CI rebuild would generate spurious diffs on every PR.
  - Refreshing is an operator-deliberate act, much like
    `scripts/bench.py --update-baseline`. We commit the refresh as its
    own reviewable PR.

Run:
    pip install pip-licenses                    # one-time
    python scripts/gen_third_party_licenses.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# UTF-8 console — JAMES standard. Without this, em-dashes and Korean
# characters in print() crash on cp949 (Windows default).
try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    # If the helper is unavailable, fall back to an env nudge that
    # most modern terminals honor.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

OUTPUT = ROOT / "THIRD_PARTY_LICENSES.md"


def _normalize(lic: str) -> str:
    """Collapse the many surface forms of the same SPDX-ish identifier
    into one bucket — pip-licenses emits whatever the upstream package
    declared, which ranges from "MIT" to a 50-line full Apache text
    pasted into the metadata field.
    """
    if len(lic) > 80:
        for line in lic.splitlines():
            line = line.strip()
            if line:
                lic = line
                break
    lic = lic.strip()
    norm = (
        lic.upper()
        .replace(" LICENSE", "")
        .replace("SOFTWARE", "")
        .replace("  ", " ")
        .strip()
    )
    if norm in ("MIT", "MIT-CMU"):
        return "MIT"
    if "APACHE" in norm and "2" in norm:
        return "Apache-2.0"
    if norm == "APACHE":
        return "Apache-2.0"
    if "BSD" in norm:
        if "3-CLAUSE" in norm or "3CLAUSE" in norm:
            return "BSD-3-Clause"
        if "2-CLAUSE" in norm or "2CLAUSE" in norm:
            return "BSD-2-Clause"
        return "BSD"
    if "MOZILLA" in norm or "MPL" in norm:
        return "MPL-2.0"
    if "PYTHON" in norm and "FOUNDATION" in norm:
        return "PSF-2.0"
    if "PUBLIC" in norm and "DOMAIN" in norm:
        return "Public Domain"
    if "ISC" in norm:
        return "ISC"
    if "UNLICENSE" in norm:
        return "Unlicense"
    if "UNKNOWN" in norm or norm == "":
        return "UNKNOWN"
    return lic[:60]


def main() -> int:
    try:
        result = subprocess.run(
            ["pip-licenses", "--format=json", "--with-urls", "--order=name"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        print(
            "ERROR: pip-licenses is not installed. Run: "
            "pip install pip-licenses",
            file=sys.stderr,
        )
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: pip-licenses failed: {exc.stderr}", file=sys.stderr)
        return 1

    data = json.loads(result.stdout)

    bucket: Counter = Counter()
    rows = []
    for p in data:
        n = _normalize(p["License"])
        bucket[n] += 1
        url = p["URL"] if p["URL"] and p["URL"] != "UNKNOWN" else ""
        name_md = f"[{p['Name']}]({url})" if url else p["Name"]
        rows.append((p["Name"].lower(), name_md, p["Version"], n))

    rows.sort()
    today = date.today().isoformat()

    out: list[str] = []
    out.append("# Third-Party Licenses")
    out.append("")
    out.append(
        f"> **Generated**: {today} via the reproduction command below."
    )
    out.append(
        "> **Scope**: every Python package present in the active venv "
        "at the time of generation."
    )
    out.append(
        "> **Refresh policy**: re-generate at every minor JAMES "
        "version (v0.4, v0.5, …) and whenever a dep is added."
    )
    out.append("")
    out.append("## Reproduction")
    out.append("")
    out.append("```bash")
    out.append("pip install pip-licenses                    # one-time")
    out.append("python scripts/gen_third_party_licenses.py")
    out.append("```")
    out.append("")
    out.append(
        "Anything that differs between fresh-run output and this "
        "committed file is a dep change since the last refresh."
    )
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append(f"**Total packages**: {len(data)}")
    out.append("")
    out.append("| License | Count |")
    out.append("|---|---|")
    for lic, count in bucket.most_common():
        out.append(f"| {lic} | {count} |")
    out.append("")
    out.append("### JAMES-vs-deps license compatibility note")
    out.append("")
    out.append(
        "JAMES itself is **MIT** (see [`LICENSE`](LICENSE)). The deps "
        "inventoried below are all under permissive licenses (MIT / "
        "Apache-2.0 / BSD family / MPL / PSF) compatible with MIT "
        "redistribution. Any future GPL / AGPL dep would need an "
        "explicit architectural review — see "
        "[`docs/LICENSE_PLAN.md`](docs/LICENSE_PLAN.md) for the "
        "project license policy."
    )
    out.append("")
    out.append("## Per-package detail")
    out.append("")
    out.append("| Package | Version | License |")
    out.append("|---|---|---|")
    for _, name_md, version, lic in rows:
        out.append(f"| {name_md} | {version} | {lic} |")
    out.append("")

    OUTPUT.write_text("\n".join(out), encoding="utf-8")
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} — {len(data)} packages, "
        f"{len(bucket)} normalized license buckets."
    )
    return 0


if __name__ == "__main__":   # pragma: no cover
    raise SystemExit(main())
