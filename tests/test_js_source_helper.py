"""Guards for tests/_js_source.py::function_body."""
from __future__ import annotations

import unittest

from tests._js_source import function_body

SAMPLE = """/* header */
function alpha() {
  const a = 1;
  // mentions function beta inside a comment
}

async function beta(x) {
  return x;
}

function gamma() {
  return 3;
}
"""


class FunctionBodyTests(unittest.TestCase):
    def test_stops_at_the_next_top_level_function(self):
        body = function_body(SAMPLE, "alpha")
        self.assertIn("const a = 1;", body)
        self.assertNotIn("return x;", body,
                         "must not bleed into the following function")

    def test_handles_an_async_neighbour(self):
        body = function_body(SAMPLE, "beta")
        self.assertIn("return x;", body)
        self.assertNotIn("return 3;", body)

    def test_last_function_runs_to_the_end(self):
        self.assertIn("return 3;", function_body(SAMPLE, "gamma"))

    def test_missing_function_raises(self):
        """A rename must fail loudly, not yield an empty slice that
        makes every assertion in the caller pass or fail for the wrong
        reason."""
        with self.assertRaises(ValueError):
            function_body(SAMPLE, "delta")

    def test_does_not_match_a_nested_or_quoted_mention(self):
        js = 'function outer() {\n  const s = "function inner() {}";\n}\n'
        self.assertIn('const s =', function_body(js, "outer"))
        with self.assertRaises(ValueError):
            function_body(js, "inner")


if __name__ == "__main__":
    unittest.main()
