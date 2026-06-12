"""v0.6 SDK.a — pack CLI scaffolder tests.

Covers:

  * `validate_pack_id` — accepts valid identifiers; rejects
    spaces / path separators / shell metachars / empty / non-str.
  * Templates render with the pack_id embedded.
  * `write_scaffold` writes 4 files to the right path.
  * `write_scaffold` refuses to overwrite an existing dir unless
    `overwrite=True`.
  * CLI entry — argparse routing + exit codes.
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from james.pack.scaffold import (
    render_license,
    render_pack_py,
    render_readme,
    render_test_pack_py,
    scaffold_files,
    validate_pack_id,
    write_scaffold,
)


class ValidatePackIdTests(unittest.TestCase):
    def test_valid_ids(self):
        for pid in (
            "a", "abc", "abc123", "legal-demo-v1",
            "finance_baseline", "x-y-z", "pack01",
        ):
            with self.subTest(pid=pid):
                validate_pack_id(pid)  # no raise

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            validate_pack_id("")

    def test_non_string_rejected(self):
        for v in (None, 123, ["abc"]):
            with self.subTest(v=v):
                with self.assertRaises(ValueError):
                    validate_pack_id(v)

    def test_uppercase_rejected(self):
        with self.assertRaises(ValueError):
            validate_pack_id("MyPack")

    def test_starts_with_digit_rejected(self):
        with self.assertRaises(ValueError):
            validate_pack_id("1pack")

    def test_spaces_rejected(self):
        with self.assertRaises(ValueError):
            validate_pack_id("my pack")

    def test_path_separators_rejected(self):
        for pid in ("a/b", "a\\b", "../etc"):
            with self.subTest(pid=pid):
                with self.assertRaises(ValueError):
                    validate_pack_id(pid)

    def test_shell_metachars_rejected(self):
        for pid in ("a;b", "a$b", "a|b", "a&b"):
            with self.subTest(pid=pid):
                with self.assertRaises(ValueError):
                    validate_pack_id(pid)


class TemplateRenderTests(unittest.TestCase):
    def test_pack_py_contains_pack_id(self):
        out = render_pack_py("legal-demo-v1")
        self.assertIn('pack_id="legal-demo-v1"', out)
        self.assertIn("from core.ontology_packs import OntologyPack", out)

    def test_pack_py_var_name_uppercase(self):
        out = render_pack_py("legal-demo-v1")
        self.assertIn("LEGAL_DEMO_V1_PACK", out)

    def test_test_pack_py_imports_pack(self):
        out = render_test_pack_py("legal-demo-v1")
        self.assertIn("from pack import LEGAL_DEMO_V1_PACK", out)

    def test_test_pack_py_has_capability_gate_test(self):
        out = render_test_pack_py("legal-demo-v1")
        self.assertIn("CapabilityNotGrantedError", out)
        self.assertIn("test_pack_cannot_mount_without_capability", out)

    def test_license_is_mit(self):
        out = render_license()
        self.assertIn("MIT License", out)
        self.assertIn("THE SOFTWARE IS PROVIDED", out)

    def test_readme_includes_pack_id_and_guide_link(self):
        out = render_readme("legal-demo-v1")
        self.assertIn("# legal-demo-v1", out)
        self.assertIn("ONTOLOGY_PACK_AUTHORING.md", out)

    def test_scaffold_files_returns_4(self):
        files = scaffold_files("test-pack-v1")
        self.assertEqual(
            set(files.keys()),
            {"pack.py", "test_pack.py", "LICENSE", "README.md"},
        )


class WriteScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="james-sdka-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_four_files(self):
        written = write_scaffold("my-pack-v1", output_dir=self.tmp)
        # `os.path.join` uses backslash on Windows; normalise to /
        # for the expected-set comparison so the test is cross-platform.
        normalised = {p.replace("\\", "/") for p in written}
        self.assertEqual(
            normalised,
            {
                "my-pack-v1/pack.py",
                "my-pack-v1/test_pack.py",
                "my-pack-v1/LICENSE",
                "my-pack-v1/README.md",
            },
        )
        for relpath in written:
            self.assertTrue(
                os.path.exists(os.path.join(self.tmp, relpath)),
                f"missing: {relpath}",
            )

    def test_creates_pack_subdir(self):
        write_scaffold("my-pack-v1", output_dir=self.tmp)
        self.assertTrue(
            os.path.isdir(os.path.join(self.tmp, "my-pack-v1")),
        )

    def test_pack_py_file_contains_template(self):
        write_scaffold("my-pack-v1", output_dir=self.tmp)
        with open(os.path.join(self.tmp, "my-pack-v1", "pack.py"),
                  encoding="utf-8") as f:
            content = f.read()
        self.assertIn('pack_id="my-pack-v1"', content)

    def test_refuse_overwrite_by_default(self):
        write_scaffold("my-pack-v1", output_dir=self.tmp)
        with self.assertRaises(FileExistsError):
            write_scaffold("my-pack-v1", output_dir=self.tmp)

    def test_overwrite_true_allows_rewrite(self):
        write_scaffold("my-pack-v1", output_dir=self.tmp)
        # Modify a file to verify overwrite restores template
        with open(os.path.join(self.tmp, "my-pack-v1", "pack.py"),
                  "w", encoding="utf-8") as f:
            f.write("modified")
        write_scaffold(
            "my-pack-v1", output_dir=self.tmp, overwrite=True,
        )
        with open(os.path.join(self.tmp, "my-pack-v1", "pack.py"),
                  encoding="utf-8") as f:
            content = f.read()
        self.assertIn("from core.ontology_packs import OntologyPack",
                      content)

    def test_invalid_pack_id_rejected(self):
        with self.assertRaises(ValueError):
            write_scaffold("Bad ID", output_dir=self.tmp)


class CliTests(unittest.TestCase):
    """Verify the argparse routing + exit codes."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="james-sdka-cli-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_command_succeeds(self):
        from james.pack.__main__ import main
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["init", "--output-dir", self.tmp, "test-pack-v1"])
        self.assertEqual(code, 0)
        self.assertIn("scaffolded", out.getvalue())
        self.assertTrue(
            os.path.isdir(os.path.join(self.tmp, "test-pack-v1")),
        )

    def test_init_invalid_id_exits_2(self):
        from james.pack.__main__ import main
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["init", "--output-dir", self.tmp, "Bad ID"])
        self.assertEqual(code, 2)
        self.assertIn("error", err.getvalue())

    def test_init_existing_no_overwrite_exits_2(self):
        from james.pack.__main__ import main
        # First call succeeds.
        out1 = io.StringIO()
        with redirect_stdout(out1):
            self.assertEqual(
                main(["init", "--output-dir", self.tmp, "p"]),
                0,
            )
        # Second call without --overwrite exits 2.
        out2 = io.StringIO()
        err2 = io.StringIO()
        with redirect_stdout(out2), redirect_stderr(err2):
            self.assertEqual(
                main(["init", "--output-dir", self.tmp, "p"]),
                2,
            )

    def test_init_overwrite_succeeds(self):
        from james.pack.__main__ import main
        out = io.StringIO()
        with redirect_stdout(out):
            main(["init", "--output-dir", self.tmp, "p"])
            self.assertEqual(
                main([
                    "init", "--overwrite",
                    "--output-dir", self.tmp, "p",
                ]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
