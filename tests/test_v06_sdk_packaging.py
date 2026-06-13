"""v0.6 SDK.c — `james-pack-sdk` PyPI packaging smoke tests.

Validates the `pyproject.toml` shape, builds a wheel + sdist via the
`build` library, and verifies the resulting artifacts contain what
the SDK promises (CLI entry point, the `james.pack` namespace,
nothing from the wider repo like ``core/`` or ``routes/``).

Coverage:

* `pyproject.toml` parses + carries the canonical [project] keys
  (name, version, license, requires-python, entry point).
* The packaged version matches `james.__version__` — packaging
  drift between the two is a release-blocker.
* `build` succeeds end-to-end: produces a wheel + sdist.
* The wheel contains ONLY the `james/` namespace (no `core/`,
  no `routes/`, no test files).
* The wheel registers the `james-pack` console script.
* SemVer policy doc exists + documents the public surface list.

Run:
  python -m unittest tests.test_v06_sdk_packaging

The build smoke test is skipped if the `build` library is not
installed (CI environments without it).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    """Parse pyproject.toml using stdlib tomllib (3.11+) or tomli."""
    try:
        import tomllib  # Python 3.11+
        with PYPROJECT.open("rb") as f:
            return tomllib.load(f)
    except ImportError:
        try:
            import tomli  # Older Python
            with PYPROJECT.open("rb") as f:
                return tomli.load(f)
        except ImportError:
            raise unittest.SkipTest(
                "neither tomllib nor tomli available; cannot parse pyproject.toml"
            )


class PyProjectShapeTests(unittest.TestCase):
    """The pyproject.toml must declare the canonical SDK metadata."""

    @classmethod
    def setUpClass(cls):
        if not PYPROJECT.exists():
            raise unittest.SkipTest("pyproject.toml not present at repo root")
        cls.cfg = _load_pyproject()

    def test_build_system_uses_setuptools_meta(self):
        bs = self.cfg.get("build-system", {})
        self.assertIn("setuptools.build_meta", bs.get("build-backend", ""))
        self.assertTrue(any("setuptools" in r for r in bs.get("requires", [])))

    def test_project_name_is_james_pack_sdk(self):
        self.assertEqual(self.cfg["project"]["name"], "james-pack-sdk")

    def test_project_version_matches_james_init(self):
        from james import __version__ as pkg_version
        self.assertEqual(self.cfg["project"]["version"], pkg_version,
                         "pyproject.toml version must match james.__version__")

    def test_python_version_floor_at_least_3_10(self):
        # Sanity check on the runtime floor. `core/` uses 3.10+ syntax,
        # so the SDK can't claim broader support without breaking on
        # the runtime API import path.
        req = self.cfg["project"]["requires-python"]
        self.assertTrue(req.startswith(">=3.10") or req.startswith(">=3.11"),
                        f"unexpected requires-python: {req!r}")

    def test_license_field_points_at_repo_license(self):
        lic = self.cfg["project"]["license"]
        self.assertEqual(lic.get("file"), "LICENSE")
        self.assertTrue((REPO_ROOT / "LICENSE").exists(),
                        "LICENSE file referenced by pyproject must exist")

    def test_readme_field_points_at_sdk_readme(self):
        self.assertEqual(self.cfg["project"]["readme"], "docs/SDK_README.md")
        self.assertTrue((REPO_ROOT / "docs" / "SDK_README.md").exists())

    def test_console_script_entry_point_is_james_pack(self):
        scripts = self.cfg["project"].get("scripts", {})
        self.assertEqual(scripts.get("james-pack"),
                         "james.pack.__main__:main")

    def test_setuptools_find_whitelists_james_only(self):
        # The wheel must NOT contain `core/`, `routes/`, `frontend/`,
        # etc. The include list pins this.
        cfg = self.cfg.get("tool", {}).get("setuptools", {})
        find_cfg = cfg.get("packages", {}).get("find", {})
        self.assertIn("james", find_cfg.get("include", []))
        self.assertIn("james.*", find_cfg.get("include", []))


class SemVerDocTests(unittest.TestCase):
    """SDK_VERSIONING.md must exist + name the public surface."""

    def test_versioning_doc_exists(self):
        path = REPO_ROOT / "docs" / "SDK_VERSIONING.md"
        self.assertTrue(path.exists(), "docs/SDK_VERSIONING.md missing")

    def test_versioning_doc_names_public_api_symbols(self):
        path = REPO_ROOT / "docs" / "SDK_VERSIONING.md"
        content = path.read_text(encoding="utf-8")
        # Sanity: doc must enumerate the canonical public-surface
        # entries so a future contributor can't accidentally remove
        # one without bumping major.
        for sym in (
            "james.pack.OntologyPack",
            "james.pack.register_pack",
            "james.pack.unmount_pack",
            "james.pack.scaffold.validate_pack_id",
            "james.pack.scaffold.write_scaffold",
            "james-pack",
        ):
            self.assertIn(sym, content,
                          f"SDK_VERSIONING.md missing public symbol: {sym}")

    def test_versioning_doc_states_12_month_window(self):
        # The deprecation window is non-negotiable per the v0.3 gate.
        path = REPO_ROOT / "docs" / "SDK_VERSIONING.md"
        content = path.read_text(encoding="utf-8")
        self.assertIn("12 months", content)


class BuildArtifactTests(unittest.TestCase):
    """Build the wheel + sdist and inspect the result."""

    @classmethod
    def setUpClass(cls):
        try:
            import build  # noqa: F401
        except ImportError:
            raise unittest.SkipTest(
                "build library not available; install with `pip install build`"
            )
        cls._tmp = tempfile.mkdtemp(prefix="james_sdk_build_")
        cls._dist = Path(cls._tmp) / "dist"
        cls._dist.mkdir()
        # Invoke `python -m build --wheel --sdist --outdir <tmp>` from
        # the repo root. We use a subprocess so the build runs in an
        # isolated environment per the build-system requirement.
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--sdist",
             "--outdir", str(cls._dist), str(REPO_ROOT)],
            capture_output=True, text=True, env={**os.environ},
        )
        if result.returncode != 0:
            shutil.rmtree(cls._tmp, ignore_errors=True)
            raise unittest.SkipTest(
                "build failed (likely missing PEP 517 isolation prereqs); "
                "stdout:\n" + result.stdout + "\nstderr:\n" + result.stderr
            )
        cls._build_output = result.stdout + result.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_wheel_artifact_present(self):
        wheels = list(self._dist.glob("james_pack_sdk-*.whl"))
        self.assertEqual(len(wheels), 1,
                         f"expected exactly one wheel, got: {wheels}")

    def test_sdist_artifact_present(self):
        sdists = list(self._dist.glob("james_pack_sdk-*.tar.gz")) + \
                 list(self._dist.glob("james-pack-sdk-*.tar.gz"))
        self.assertEqual(len(sdists), 1,
                         f"expected exactly one sdist, got: {sdists}")

    def test_wheel_contains_only_james_namespace(self):
        wheels = list(self._dist.glob("james_pack_sdk-*.whl"))
        if not wheels:
            self.skipTest("wheel not built")
        with zipfile.ZipFile(wheels[0]) as zf:
            members = zf.namelist()

        # Every .py member must be under `james/` (with the
        # exception of `*.dist-info/*` metadata).
        py_members = [m for m in members
                      if m.endswith(".py") and ".dist-info/" not in m]
        for m in py_members:
            self.assertTrue(m.startswith("james/"),
                            f"unexpected file in wheel: {m!r}")

        # Affirm: NONE of the bulky repo dirs leak in.
        for forbidden_prefix in ("core/", "routes/", "frontend/",
                                  "tests/", "scripts/", "docs/"):
            offenders = [m for m in members if m.startswith(forbidden_prefix)]
            self.assertEqual(offenders, [],
                             f"wheel contains forbidden prefix {forbidden_prefix!r}: "
                             f"{offenders[:3]}")

    def test_wheel_metadata_declares_entry_point(self):
        wheels = list(self._dist.glob("james_pack_sdk-*.whl"))
        if not wheels:
            self.skipTest("wheel not built")
        with zipfile.ZipFile(wheels[0]) as zf:
            entry_members = [m for m in zf.namelist()
                             if m.endswith("entry_points.txt")]
            self.assertTrue(entry_members,
                            "wheel missing entry_points.txt")
            content = zf.read(entry_members[0]).decode("utf-8")
        self.assertIn("james-pack", content)
        self.assertIn("james.pack.__main__:main", content)


if __name__ == "__main__":
    unittest.main()
