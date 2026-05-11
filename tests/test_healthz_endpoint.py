"""[2026-05-10] /healthz readiness probe.

k8s / docker / uptime monitor 표준 경로. 인증 없이 process-alive 응답.
실 가용성 (DB/vector/LLM) 은 /status/ 에서 별도 보고.

Run:
    python -m unittest tests.test_healthz_endpoint
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class HealthzRouteTests(unittest.TestCase):
    """server_llmwiki.py 안에 /healthz 핸들러가 정의되어 있는지 검증."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "server_llmwiki.py").read_text(encoding="utf-8")

    def test_healthz_route_defined(self):
        # 데코레이터 + 함수 시그니처가 모두 존재해야.
        self.assertRegex(
            self.src,
            r'@app\.get\("/healthz"',
            "/healthz 데코레이터 라우트 누락",
        )
        self.assertRegex(
            self.src,
            r'async\s+def\s+healthz\s*\(',
            "healthz 핸들러 함수 정의 누락",
        )

    def test_healthz_returns_status_ok(self):
        # 본문이 {"status": "ok"} 형태인지 확인.
        m = re.search(
            r'async\s+def\s+healthz[^:]*:\s*\n\s*return\s*(\{[^}]+\})',
            self.src,
        )
        self.assertIsNotNone(m, "healthz 함수가 dict 를 즉시 반환하지 않음")
        body = m.group(1)
        self.assertIn('"status"', body)
        self.assertIn('"ok"', body)

    def test_healthz_excluded_from_openapi_schema(self):
        # operational endpoint — public schema 노출 X.
        self.assertRegex(
            self.src,
            r'@app\.get\("/healthz"[^)]*include_in_schema\s*=\s*False',
            "healthz 가 OpenAPI schema 에 노출되고 있음",
        )


class HealthzNoAuthTests(unittest.TestCase):
    """인증 없는 endpoint — Depends(get_role_from_request) 등 가드 X."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "server_llmwiki.py").read_text(encoding="utf-8")

    def test_no_auth_dependency(self):
        # healthz 함수 시그니처에 api_key/role/Depends 등이 없어야.
        m = re.search(
            r'async\s+def\s+healthz\s*\(([^)]*)\)\s*:',
            self.src,
        )
        self.assertIsNotNone(m, "healthz 함수 시그니처를 못 찾음")
        sig = m.group(1).strip()
        self.assertEqual(
            sig, "",
            f"healthz 가 인증 의존성을 가짐 — readiness probe 는 인증 X "
            f"(현재 시그니처: {sig!r})",
        )


if __name__ == "__main__":
    unittest.main()
